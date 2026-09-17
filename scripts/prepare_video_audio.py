"""Generate narration, aligned captions and an original quiet music bed.

Uses the public promotional script only. No application credentials or data are read.
Requires edge-tts, numpy and ffmpeg/ffprobe on PATH.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import string
import subprocess
import wave

import edge_tts
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'video/public'
TEMP = ROOT / '.run/video_audio'
VOICE = 'en-SG-WayneNeural'
TOKEN_EDGE_PUNCTUATION = string.punctuation.replace('-', '').replace("'", '') + '“”‘’'


def duration(path):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                 'format=duration', '-of', 'default=nw=1:nk=1', str(path)]).decode().strip())


def stamp(ms):
    ms = round(ms)
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def narration_tokens(narration):
    """Return non-whitespace tokens with their original character spans."""
    return [
        {'text': match.group(), 'start': match.start(), 'end': match.end()}
        for match in re.finditer(r'\S+', narration)
    ]


def aligned_caption_groups(narration, boundaries):
    """Align Edge word boundaries to punctuation-preserving narration groups."""
    tokens = narration_tokens(narration)
    if len(tokens) != len(boundaries):
        raise ValueError(
            f'Narration has {len(tokens)} whitespace tokens but Edge returned '
            f'{len(boundaries)} word boundaries.'
        )
    for index, (token, boundary) in enumerate(zip(tokens, boundaries), start=1):
        source_word = token['text'].strip(TOKEN_EDGE_PUNCTUATION)
        if source_word.casefold() != boundary['text'].casefold():
            raise ValueError(
                f'Word boundary {index} does not match narration: '
                f'{token["text"]!r} != {boundary["text"]!r}'
            )

    groups, current = [], []
    for token, boundary in zip(tokens, boundaries):
        current.append((token, boundary))
        first_token = current[0][0]
        text = narration[first_token['start']:token['end']]
        word_count = len(current)
        sentence_break = bool(re.search(r'[.!?;:]$', token['text'])) and word_count >= 3
        comma_break = token['text'].endswith(',') and word_count >= 5
        if word_count >= 8 or len(text) > 64 or sentence_break or comma_break:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def scene_captions(scene, boundaries, tempo):
    """Build caption cues using raw Edge timing and the actual, unrounded tempo."""
    narration = scene['narration']
    start_ms = (scene['start'] + .55) * 1000
    scene_limit_ms = (scene['start'] + scene['duration'] - .2) * 1000
    cues = []
    for group in aligned_caption_groups(narration, boundaries):
        first_token, first_word = group[0]
        last_token, last_word = group[-1]
        begin = start_ms + first_word['offset'] / 10000 / tempo
        end = start_ms + (last_word['offset'] + last_word['duration']) / 10000 / tempo + 200
        text = narration[first_token['start']:last_token['end']]
        cues.append({
            'text': text,
            'startMs': round(begin),
            'endMs': round(min(end, scene_limit_ms)),
            'timestampMs': None,
            'confidence': None,
        })
    return cues


def validate_captions(captions, runtime_ms=114000):
    if not captions:
        raise ValueError('No captions were generated.')
    if len(captions) != 40:
        raise ValueError(f'Expected 40 caption cues, generated {len(captions)}.')
    for index, cue in enumerate(captions):
        if not cue['text'].strip():
            raise ValueError(f'Caption {index + 1} is empty.')
        if not 0 <= cue['startMs'] < cue['endMs'] <= runtime_ms:
            raise ValueError(f'Caption {index + 1} is outside the {runtime_ms} ms runtime.')
        if index and captions[index - 1]['endMs'] >= cue['startMs']:
            raise ValueError(f'Caption {index + 1} overlaps the preceding cue.')


def validate_audio_placement(scenes, metadata):
    if len(scenes) != len(metadata):
        raise ValueError('Narration metadata does not cover every scene.')
    previous_end = 0.0
    for scene, record in zip(scenes, metadata):
        if scene['id'] != record['id']:
            raise ValueError('Narration metadata is out of scene order.')
        audio_start = record['start']
        audio_end = audio_start + record['duration']
        scene_end = scene['start'] + scene['duration']
        if audio_start < previous_end:
            raise ValueError(f'Scene {scene["id"]} narration overlaps the preceding clip.')
        if audio_end > scene_end:
            raise ValueError(
                f'Scene {scene["id"]} narration ends at {audio_end:.3f}s, '
                f'after its {scene_end:.3f}s scene boundary.'
            )
        previous_end = audio_end


async def main():
    TEMP.mkdir(parents=True, exist_ok=True)
    (PUBLIC / 'audio').mkdir(parents=True, exist_ok=True)
    scenes = json.loads((ROOT / 'docs/video/NARRATION.json').read_text(encoding='utf-8'))
    captions, metadata = [], []
    for scene in scenes:
        ident = scene['id']
        raw = TEMP / f'{ident:02d}.mp3'
        boundaries_file = TEMP / f'{ident:02d}.json'
        source_file = TEMP / f'{ident:02d}.txt'
        fingerprint = scene['narration'] + '|rate=+8%'
        if not raw.exists() or not boundaries_file.exists() or not source_file.exists() or source_file.read_text() != fingerprint:
            words = []
            speech = edge_tts.Communicate(scene['narration'], VOICE, rate='+8%', boundary='WordBoundary')
            with raw.open('wb') as audio:
                async for chunk in speech.stream():
                    if chunk['type'] == 'audio':
                        audio.write(chunk['data'])
                    elif chunk['type'] == 'WordBoundary':
                        words.append({k: chunk[k] for k in ('text', 'offset', 'duration')})
            boundaries_file.write_text(json.dumps(words), encoding='utf-8')
            source_file.write_text(fingerprint)
        words = json.loads(boundaries_file.read_text())
        raw_seconds = duration(raw)
        available = scene['duration'] - 1.1
        tempo = max(1.0, raw_seconds / available)
        if tempo > 1.30:
            raise ValueError(f'Scene {ident} narration is too long: {raw_seconds:.1f}s for {available:.1f}s. Edit the script.')
        output = PUBLIC / 'audio' / f'voice-{ident:02d}.mp3'
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(raw),'-af',
                        f'atempo={tempo:.6f},loudnorm=I=-18:TP=-2:LRA=7',
                        '-ar','48000','-b:a','160k',str(output)],check=True)
        # Audio uses the six-decimal filter value above. Caption regeneration uses
        # the published four-decimal metadata value to remain byte-for-byte stable
        # with the reviewed JSON/SRT (the difference is at most one millisecond).
        metadata_tempo = round(tempo, 4)
        captions.extend(scene_captions(scene, words, metadata_tempo))
        metadata.append({'id':ident,'voice':VOICE,'start':scene['start']+.55,
                         'duration':duration(output),'tempo':metadata_tempo})
        print(f'Scene {ident:02d}: {duration(output):.2f}s narration / {scene["duration"]}s scene',flush=True)
    for i in range(len(captions)-1):
        captions[i]['endMs'] = min(captions[i]['endMs'],captions[i+1]['startMs']-1)
    validate_captions(captions)
    validate_audio_placement(scenes, metadata)
    (PUBLIC/'captions.json').write_text(json.dumps(captions,indent=2),encoding='utf-8')
    (PUBLIC/'audio/narration-metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    srt='\n\n'.join(f'{i+1}\n{stamp(c["startMs"])} --> {stamp(c["endMs"])}\n{c["text"]}' for i,c in enumerate(captions))+'\n'
    (PUBLIC/'ngeebula-promo.en.srt').write_text(srt,encoding='utf-8')
    music()


def music():
    # Original D-minor ambient motif; no samples or third-party compositions.
    sr=32000
    length=114
    x=np.zeros(sr*length,dtype=np.float64)
    chords=[[146.832,174.614,220.0],[116.541,146.832,174.614],
            [130.813,174.614,220.0],[130.813,164.814,195.998]]
    for section in range(29):
        start=section*4
        count=min(sr*5,len(x)-start*sr)
        if count<=0:break
        t=np.arange(count)/sr
        envelope=np.minimum(t/.7,1)*np.minimum((count/sr-t)/1.7,1)
        for hz in chords[section%4]:
            pad=(np.sin(2*np.pi*hz*t)+.18*np.sin(2*np.pi*hz*2*t))*.028
            x[start*sr:start*sr+count]+=pad*envelope
    for beat in np.arange(1,111,1.25):
        start=int(beat*sr); count=min(sr//2,len(x)-start);t=np.arange(count)/sr
        hz=chords[int(beat//4)%4][int(beat/1.25)%3]*2
        x[start:start+count]+=np.sin(2*np.pi*hz*t)*np.exp(-t*9)*.022
    t=np.arange(len(x))/sr
    x*=np.minimum(t/3,1)*np.minimum((length-t)/4,1)
    stereo=np.column_stack([x,np.roll(x,190)*.92])
    wav=TEMP/'original-score.wav'
    with wave.open(str(wav),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(sr)
        f.writeframes((np.clip(stereo,-1,1)*32767).astype('<i2').tobytes())
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(wav),'-af','loudnorm=I=-32:TP=-6:LRA=6',
                    '-b:a','128k',str(PUBLIC/'audio/original-score.mp3')],check=True)
    print('Original ambient score, aligned JSON captions and SRT ready.',flush=True)


if __name__=='__main__':
    asyncio.run(main())
