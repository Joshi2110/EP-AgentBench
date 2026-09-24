"""Reviewed trajectory conversion and final-assistant-only tokenization."""

import hashlib
import json
from pathlib import Path

from .tools import parse_call


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def reviewed_examples(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'reviews.json').read_text())
    if manifest.get('schema') != 'epagent.sft-review.v1':
        raise ValueError('Expected an explicit SFT review manifest')
    examples = {'train': [], 'valid': []}
    families, episode_ids = {}, set()
    for review in manifest['episodes']:
        ident, split, family = (review[k] for k in ('episode_id', 'split', 'family'))
        if ident in episode_ids or split not in examples:
            raise ValueError('Duplicate episode or invalid split')
        episode_ids.add(ident)
        if family in families and families[family] != split:
            raise ValueError('A task family cannot cross train/validation splits')
        families[family] = split
        if (review.get('origin') != 'authored-synthetic-fixture' or not review.get('rights')
                or not review.get('review')):
            raise ValueError('Phase 1 accepts reviewed project-authored synthetic demonstrations only')
        path = directory / review['trace']
        if path.parent.resolve() != directory.resolve() or path.is_symlink():
            raise ValueError('Trace must be a regular file in the reviewed directory')
        if digest(path) != review['trace_sha256']:
            raise ValueError('Reviewed trajectory hash changed')
        events = [json.loads(line) for line in path.read_text().splitlines()]
        if (not events or events[0]['event'] != 'episode_start'
                or events[0]['data']['task_id'] != 'synthetic:' + ident):
            raise ValueError('Hall tasks and unregistered trajectories are excluded from SFT')
        if any(e['schema'] != 'epagent.episode.v1' or e['episode_id'] != ident for e in events):
            raise ValueError('Mixed trajectory schema or episode IDs')
        requests, responses, observations = {}, {}, {}
        for index, event in enumerate(events, 1):
            if event['sequence'] != index:
                raise ValueError('Trace sequence must be complete and ordered')
            target = {'model_request': requests, 'assistant': responses, 'tool_result': observations}.get(event['event'])
            if target is not None:
                step = event['data']['step']
                if step in target:
                    raise ValueError('Duplicate step event')
                target[step] = event['data']
        selected = review['selected_assistant_steps']
        if (not selected or len(set(selected)) != len(selected) or not set(selected) <= responses.keys()
                or requests.keys() != responses.keys() or observations.keys() != responses.keys()):
            raise ValueError('Incomplete trace or invalid reviewed step selection')
        previous = None
        for step in sorted(responses):
            messages = requests[step]['messages']
            if not messages or messages[0]['role'] != 'system' or messages[-1]['role'] != 'user':
                raise ValueError('Expected system instruction and user/tool context')
            if previous is not None:
                prior_step, prior_messages = previous
                if (messages[:-2] != prior_messages or messages[-2] !=
                        {'role': 'assistant', 'content': responses[prior_step]['text']} or
                        json.loads(messages[-1]['content'])['tool_result'] != observations[prior_step]['observation']):
                    raise ValueError('Observation/history does not match recorded tool execution')
            previous = step, messages
            if step not in selected:
                continue
            text = responses[step]['text']
            tool, _ = parse_call(text)
            if 'error' in observations[step]['observation']:
                raise ValueError('Failed tool edits/calls must be context, not positive targets')
            kinds = []
            for i, message in enumerate(messages):
                if message['role'] == 'system':
                    kinds.append('system_instruction')
                elif message['role'] == 'assistant':
                    kinds.append('assistant_history')
                elif message['role'] == 'user':
                    kinds.append('user_instruction' if i == 1 else 'tool_observation')
                else:
                    raise ValueError('Unexpected role in EP-Agent trajectory')
            examples[split].append({'schema': 'epagent.sft-example.v1', 'episode_id': ident,
                'family': family, 'step': step, 'source_trace_sha256': review['trace_sha256'],
                'messages': messages + [{'role': 'assistant', 'content': text}],
                'message_kinds': kinds + ['assistant_finish' if tool == 'finish' else 'assistant_tool_call']})
    if not all(examples.values()):
        raise ValueError('Both train and validation examples are required')
    return examples


def tokenize_example(example, tokenizer, max_length):
    messages = example['messages']
    if messages[-1]['role'] != 'assistant':
        raise ValueError('The supervised message must be assistant-generated')
    prompt = list(tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True))
    full = list(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False))
    if full[:len(prompt)] != prompt:
        raise ValueError('Chat template/tokenization changed the context prefix; cannot mask safely')
    eos = tokenizer.eos_token_id
    completion = full[len(prompt):]
    if completion.count(eos) != 1:
        raise ValueError('Expected one assistant end-of-turn token')
    # Include the actual end-of-turn token; exclude the template's following newline.
    end = len(prompt) + completion.index(eos) + 1
    tokens = full[:end]
    if not prompt or end <= len(prompt) + 1 or end > max_length:
        raise ValueError('Empty/oversize supervised example; no silent truncation')
    return {'tokens': tokens, 'offset': len(prompt), 'length': end,
            'supervised_tokens': end - len(prompt), 'episode_id': example['episode_id'], 'step': example['step']}


def assistant_loss(model, batch, lengths):
    """Only targets [assistant content, EOS]; never prompt, observation, or padding."""
    import mlx.core as mx
    import mlx.nn as nn
    logits = model(batch[:, :-1])
    targets = batch[:, 1:]
    positions = mx.arange(1, batch.shape[1])
    mask = (positions >= lengths[:, 0:1]) & (positions < lengths[:, 1:2])
    losses = nn.losses.cross_entropy(logits, targets)
    count = mask.sum()
    return mx.where(mask, losses, 0).astype(mx.float32).sum() / count, count
