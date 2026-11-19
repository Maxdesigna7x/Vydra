"""Verified model-specific inference data and lazily initialized FAISS classifiers."""
import csv
import json

import numpy as np
import torch
from torch import nn

try:
    from .model_profiles import PROFILES, profile_root, verify_manifest
except ImportError:
    from model_profiles import PROFILES, profile_root, verify_manifest


class ProfileRuntime:
    def __init__(self, profile, classifier, engine):
        self.id = profile
        self.classifier = classifier
        self.engine = engine
        self.directory = profile_root() / profile
        self.dimension = PROFILES[profile]["dimension"]
        self.heads = {}
        self.train = None
        self.classes = None
        self.lookup = None
        self.allowed = None
        self.manifest = None
        self.train_manifest = None
        if profile != "prostt5":
            self.manifest = verify_manifest(self.directory, "manifest.json", profile)
            self.classes = json.loads((self.directory / "labels.json").read_text())
        if self.manifest and self.manifest["prototypes_from_train"]:
            legacy = verify_manifest(self.directory, "train_manifest.json", profile)
            if any(legacy[key] != self.manifest[key] for key in ("split_sha256", "source_matrix_sha256")):
                raise ValueError("Phage prototype vectors differ from the selected encoder or split")
            self.train = np.load(self.directory / "train_vectors.npy", mmap_mode="r", allow_pickle=False)
        self.m4_index = None
        if classifier == "faiss":
            self.train_manifest = verify_manifest(self.directory, "m4_manifest.json", profile)
            if self.manifest and any(self.manifest[key] != self.train_manifest[key]
                                     for key in ("split_sha256", "source_matrix_sha256")):
                raise ValueError("M4 bank differs from the selected encoder or split")

    def encoder(self):
        from transformers import AutoTokenizer, EsmModel
        model_path = self.directory / "encoder"
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        if self.id in {"esm2-8m", "esm2-35m"}:
            self.lookup = np.full(256, tokenizer.unk_token_id, dtype=np.int64)
            self.allowed = np.zeros(256, dtype=bool)
            for token, index in tokenizer.get_vocab().items():
                if len(token) == 1 and ord(token) < 128:
                    self.lookup[ord(token)] = index
                    self.allowed[ord(token)] = True
        dtype = torch.float16 if self.engine.device.type == "cuda" else torch.float32
        model = EsmModel.from_pretrained(model_path, local_files_only=True, add_pooling_layer=False,
                                         torch_dtype=dtype)
        return tokenizer, model.to(self.engine.device).eval()

    def pool(self, sequences, tokenizer, model):
        if self.lookup is None:
            inputs = tokenizer(sequences, padding=True, return_tensors="pt").to(self.engine.device)
        else:
            payloads = []
            for sequence in sequences:
                raw = np.frombuffer(sequence.encode("ascii", errors="replace"), dtype=np.uint8)
                if sequence.isascii() and self.allowed[raw].all():
                    tokens = np.empty(len(raw) + 2, dtype=np.int64)
                    tokens[0], tokens[-1] = tokenizer.cls_token_id, tokenizer.eos_token_id
                    tokens[1:-1] = self.lookup[raw]
                else:
                    tokens = tokenizer(sequence, return_attention_mask=False)["input_ids"]
                payloads.append(tokens)
            ids = np.full((len(sequences), max(map(len, payloads))), tokenizer.pad_token_id, dtype=np.int64)
            mask = np.zeros_like(ids)
            for row, tokens in enumerate(payloads):
                ids[row, :len(tokens)] = tokens
                mask[row, :len(tokens)] = 1
            inputs = {"input_ids": torch.from_numpy(ids).to(self.engine.device),
                      "attention_mask": torch.from_numpy(mask).to(self.engine.device)}
        with torch.inference_mode():
            hidden = model(**inputs).last_hidden_state
            attention = inputs["attention_mask"].bool()
            keep = attention.clone()
            keep[:, 0] = False
            keep[torch.arange(len(sequences), device=keep.device), attention.sum(1) - 1] = False
            if not keep.any(dim=1).all():
                raise ValueError("An input window has no residues")
            pooled = (hidden.float() * keep.unsqueeze(-1)).sum(1) / keep.sum(1, keepdim=True)
        return pooled.cpu().numpy()

    def mlp(self, name):
        if name not in self.heads:
            classes = self.classes[name]
            layers = nn.Sequential(nn.Linear(self.dimension, 512), nn.BatchNorm1d(512), nn.ReLU(),
                                   nn.Dropout(.3), nn.Linear(512, 256), nn.BatchNorm1d(256),
                                   nn.ReLU(), nn.Dropout(.2), nn.Linear(256, len(classes)))
            model = nn.Module()
            model.layers = layers
            state = torch.load(self.directory / "heads" / f"{name[:2]}.pt", map_location="cpu", weights_only=True)
            model.load_state_dict(state, strict=True)
            self.heads[name] = model.to(self.engine.device).eval()
        return self.heads[name].layers

    def predict(self, name, vector):
        classes = self.classes[name]
        with torch.inference_mode():
            x = torch.from_numpy(vector).to(self.engine.device).unsqueeze(0)
            values = self.mlp(name)(x).softmax(dim=1)[0]
            score, label = values.max(0)
        return classes[int(label)], float(score)

    def predict_m4(self, vector):
        if self.m4_index is None:
            matrix = np.load(self.directory / "m4_vectors.npy", mmap_mode="r", allow_pickle=False)
            labels = np.load(self.directory / "m4_targets.npy", allow_pickle=False)
            classes = json.loads((self.directory / "m4_classes.json").read_text())
            if (matrix.ndim != 2 or matrix.shape != (len(labels), self.dimension)
                    or matrix.dtype != np.float32 or not len(labels)
                    or labels.min() < 0 or labels.max() >= len(classes)):
                raise ValueError("Invalid M4 reference bank")
            if self.classes is not None and self.classes[self.engine.MODEL_NAMES[3]] != classes:
                raise ValueError("M4 class order differs from the MLP vocabulary")
            self.m4_index = self.engine.build_faiss_index(matrix)
            self.m4_matrix, self.m4_labels, self.m4_classes = matrix, labels, classes
        scores, ids = self.engine.gpu_faiss.search_index(
            self.m4_index, vector.reshape(1, -1), min(len(self.m4_labels), 2))
        index, score = int(ids[0, 0]), float(scores[0, 0])
        if index < 0:
            raise ValueError("FAISS returned no neighbor for M4")
        if scores.shape[1] == 2 and abs(score - scores[0, 1]) <= 2e-7:
            exact = self.m4_matrix @ vector
            index = int(exact.argmax())
            score = float(exact[index])
        return self.m4_classes[int(self.m4_labels[index])], score

    def prototypes(self, dataset_type):
        branch = "Struct" if dataset_type == "structural" else "Non_Struct"
        with (self.directory / f"{branch}_prototype_bank.csv").open(newline="") as stream:
            records = list(csv.DictReader(stream))
        if self.manifest["prototypes_from_train"]:
            train = self.train if self.train is not None else np.load(
                self.directory / "train_vectors.npy", mmap_mode="r", allow_pickle=False)
            positions = np.load(self.directory / f"{branch}_prototype_positions.npy", allow_pickle=False)
            vectors = train[positions]
        else:
            vectors = np.load(self.directory / f"{branch}_prototypes.npy", mmap_mode="r", allow_pickle=False)
        if vectors.shape != (len(records), self.dimension):
            raise ValueError(f"Prototype dimensions or rows do not match for {branch}")
        raw = {}
        for name in sorted({r["class_name"] for r in records}):
            rows = [i for i, item in enumerate(records) if item["class_name"] == name]
            raw[name] = dict(prototypes=vectors[rows],
                             seq_ids=[records[i]["seq_id"] for i in rows],
                             cluster_ids=[int(records[i]["cluster_id"]) for i in rows],
                             prototype_source="frozen ProstT5 representatives")
        return raw
