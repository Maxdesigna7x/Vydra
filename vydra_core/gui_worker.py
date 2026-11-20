"""Isolated local GUI job, using the same CLI and folder output contracts."""
from pathlib import Path
import argparse
import json
import os
import time
import traceback
from datetime import datetime, timezone
from folder_inputs import prepare_resumable_inputs, postprocess, write_json, resolve_model_path
from vydra_cli import build_parser, command_predict
from model_profiles import PROFILES, profile_root
from report_payloads import update_report_timing


class PhaseRate:
    """Measure new work this session, excluding units loaded from a checkpoint."""

    def __init__(self):
        self.baseline = None
        self.last_count = None
        self.rate = None

    def observe(self, count, now):
        if self.baseline is None or count < self.last_count:
            self.baseline = (count, now)
            self.last_count = count
            self.rate = None
            return None
        initial_count, initial_time = self.baseline
        if count > self.last_count and now > initial_time:
            self.rate = (count - initial_count) / (now - initial_time)
            self.last_count = count
        return self.rate


def run(path):
    state = json.loads(path.read_text())
    started = time.monotonic()

    def update(**values):
        state.update(values)
        state['elapsed_seconds'] = round(time.monotonic() - started, 1)
        write_json(path, state)

    try:
        output = Path(state['output'])
        source = Path(state['input'])
        update(status='running', stage='Preparing input', processed=None)
        output.mkdir(parents=True, exist_ok=True)
        combined, _, manifest, preparation = prepare_resumable_inputs(
            source if source.is_dir() else source.parent, output,
            input_files=None if source.is_dir() else [source], resume=state.get("resume", False))
        update(total=preparation['input_sequences'], excluded=preparation['excluded_sequences'])
        args_list = ['predict', '--fasta', str(combined), '--format', 'jsonl',
                     '--output', str(output / 'predicciones_motor_temporal.jsonl'),
                     '--device', state['device'], '--no-report', '--language', 'en']
        if state.get('resume') and (output / 'predicciones_motor_temporal.jsonl.checkpoint' / 'identity.json').is_file():
            args_list.append('--resume')
        profile = state.get('model') or 'prostt5'
        classifier = state.get('classifier') or 'mlp'
        args_list.extend(['--model', profile, '--m4-classifier', classifier])
        if state['offline']:
            args_list.append('--offline')
        if state.get('batch_size'):
            args_list.extend(['--batch-size', str(state['batch_size'])])
        from checkpoints import estimate_storage, check_space, atomic_json
        estimate = estimate_storage(len(manifest), combined.stat().st_size, dimension=PROFILES[profile]['dimension'], report=state['report'])
        update(storage_estimate=estimate)
        atomic_json(output / 'estimacion_espacio.json', estimate)
        if not state.get('resume'):
            check_space(output, estimate['estimated_total_bytes'])
        update(stage='Locating protein model')
        if profile == 'prostt5':
            model_path = resolve_model_path(None, state['offline'], 'en')
            os.environ['VYDRA_PROSTT5_PATH'] = str(model_path)
        else:
            model_path = profile_root() / profile / 'encoder'
        args = build_parser('en').parse_args(args_list)
        # The resolver has already downloaded or validated the local snapshot.
        args.offline = True

        classification_rate = PhaseRate()
        embedding_rate = PhaseRate()

        def progress(done, total):
            saved_path = output / 'predicciones_motor_temporal.jsonl.checkpoint' / 'progress.json'
            saved_at = json.loads(saved_path.read_text()).get('saved_at') if saved_path.is_file() else None
            update(stage='Classifying proteins', processed=done, total=total,
                   phase_rate=classification_rate.observe(done, time.monotonic()),
                   last_progress_at=time.time(), checkpoint_saved_at=saved_at,
                   batch_size_active=0, work_started_at=time.time())

        def chunk_progress(details):
            counts = (details['processed'], details['chunks_done'])
            # The first embedding callback reports recovered units before the model loads.
            # Start timing with the first real batch, even when resuming from a checkpoint.
            if details['computing'] or embedding_rate.baseline is not None:
                embedding_rate.observe(details['chunks_done'], time.monotonic())
            previous = (state.get('processed'), state.get('chunks_done'))
            values = dict(stage='Generating embeddings', processed=details['processed'],
                          total=details['total'], chunks_done=details['chunks_done'],
                          chunks_total=details['chunks_total'],
                          phase_rate=embedding_rate.rate, checkpoint_saved_at=details['checkpoint_saved_at'],
                          batch_size_active=details['batch_size'])
            if details['computing'] and not state.get('batch_size_active'):
                values['work_started_at'] = time.time()
            if counts != previous or not state.get('last_progress_at'):
                values['last_progress_at'] = time.time()
            update(**values)

        args._storage_report = state["report"]
        args._progress_callback = progress
        args._chunk_progress_callback = chunk_progress
        args._storage_callback = lambda value: update(storage_estimate=value)
        update(stage='Loading models and generating embeddings', processed=None)
        command_predict(args)
        update(stage='Writing results', processed=state['total'], phase_rate=None, batch_size_active=0)
        engine_metadata_path = output / 'predicciones_motor_temporal.jsonl.metadata.json'
        engine_metadata = json.loads(engine_metadata_path.read_text()) if engine_metadata_path.is_file() else {}
        results = postprocess(output / 'predicciones_motor_temporal.jsonl', output, manifest)
        inference_seconds = round(time.monotonic() - started, 6)
        metadata = {
            'started_at': state.get('created_at'),
            'status': 'complete', 'output_language': 'en', 'input_root': str(source if source.is_dir() else source.parent),
            'output_root': str(output), 'result': results, 'preparation': preparation,
            'device_requested': state['device'], 'offline': state['offline'], 'gui_run_id': state['id'],
            'model_path': str(model_path), 'model_profile': profile, 'classifier': classifier, 'm4_classifier': classifier,
            'inference_seconds': inference_seconds,
            'profile_artifacts': engine_metadata.get('profile_artifacts'),
            'classifier_artifacts': engine_metadata.get('classifier_artifacts'),
            'original_sequences_path': str(output / 'original_sequences.jsonl'),
        }
        write_json(output / 'metadata_inferencia.json', metadata)
        if state['report']:
            update(stage='Generating report')
            from inference_report import generate_report, DEFAULT_TAXONOMY
            report_started = time.monotonic()
            generate_report(output / 'predicciones_completas.jsonl', output / 'informe_inferencia',
                            taxonomy_path=DEFAULT_TAXONOMY if DEFAULT_TAXONOMY.is_file() else None,
                            language='en')
            state['report_path'] = str(output / 'informe_inferencia' / 'informe.html')
            metadata['report_seconds'] = round(time.monotonic() - report_started, 6)
        metadata['total_processing_seconds'] = round(time.monotonic() - started, 6)
        metadata['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'metadata_inferencia.json', metadata)
        if state['report']:
            update_report_timing(output / 'informe_inferencia', metadata)
        update(status='complete', stage='Completed', result=results)
    except Exception as exc:
        traceback.print_exc()
        update(status='failed', stage='Failed', error=str(exc))
        return 1
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('state', type=Path)
    raise SystemExit(run(parser.parse_args().state))
