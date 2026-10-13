"""Isolated local GUI job, using the same CLI and folder output contracts."""
from pathlib import Path
import argparse
import json
import os
import time
import traceback
from datetime import datetime, timezone
from folder_inputs import prepare_inputs, postprocess, write_json, resolve_model_path
from vydra_cli import build_parser, command_predict
from report_payloads import update_report_timing


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
        combined, _, manifest, preparation = prepare_inputs(
            source if source.is_dir() else source.parent, output,
            input_files=None if source.is_dir() else [source])
        update(total=preparation['input_sequences'], excluded=preparation['excluded_sequences'])
        args_list = ['predict', '--fasta', str(combined), '--format', 'jsonl',
                     '--output', str(output / 'predicciones_motor_temporal.jsonl'),
                     '--device', state['device'], '--no-report', '--language', 'en']
        if state['offline']:
            args_list.append('--offline')
        if state.get('batch_size'):
            args_list.extend(['--batch-size', str(state['batch_size'])])
        update(stage='Locating protein model')
        model_path = resolve_model_path(None, state['offline'], 'en')
        os.environ['VYDRA_PROSTT5_PATH'] = str(model_path)
        args = build_parser('en').parse_args(args_list)
        # The resolver has already downloaded or validated the local snapshot.
        args.offline = True

        def progress(done, total):
            if done == 1 or done == total or done % 25 == 0:
                update(stage='Classifying proteins', processed=done, total=total)

        args._progress_callback = progress
        update(stage='Loading models and generating embeddings', processed=None)
        command_predict(args)
        update(stage='Writing results', processed=state['total'])
        results = postprocess(output / 'predicciones_motor_temporal.jsonl', output, manifest)
        inference_seconds = round(time.monotonic() - started, 6)
        metadata = {
            'started_at': state.get('created_at'),
            'status': 'complete', 'output_language': 'en', 'input_root': str(source if source.is_dir() else source.parent),
            'output_root': str(output), 'result': results, 'preparation': preparation,
            'device_requested': state['device'], 'offline': state['offline'], 'gui_run_id': state['id'],
            'model_path': str(model_path),
            'inference_seconds': inference_seconds,
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
