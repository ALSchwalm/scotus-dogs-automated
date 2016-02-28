import math
import json
import os
import urllib.request
import random
from moviepy.editor import *
from random import choice, uniform

""" A mapping of Justices' real names to their 'resource' name
"""
JUSTICE_MAPPING = {
    "John G. Roberts, Jr.": "roberts",
    "Antonin Scalia": "scalia",
    "Ruth Bader Ginsburg": "ginsburg",
    "Sonia Sotomayor": "sotomayor",
    "Elena Kagan": "kagan",
    "Stephen G. Breyer": "breyer",
    "Anthony M. Kennedy": "kennedy",
    "Samuel A. Alito, Jr.": "alito",
    "Clarence Thomas": "thomas"
}

MAX_MISC_TIME = 4
MAX_RELATED_TIME = 7
MIN_CLIP_DURATION = 1.8
RECENT_SPEAKER_THRESHOLD = 6


def random_clip(video, duration):
    assert(duration < video.duration)
    start = uniform(0, video.duration - duration)
    return video.subclip(start, start+duration)


def generate_video_for_speaker(speaker, duration, resources, no_skip=False):
    speaker_resources = resources[speaker]
    misc_resources = resources["misc"]

    clips = []
    while duration > MIN_CLIP_DURATION or no_skip:
        no_skip = False

        c = choice(speaker_resources)
        if c.duration > duration:
            clips.append(random_clip(c, duration))
            duration = 0
        else:
            clips.append(c)
            duration -= c.duration
            m = choice(misc_resources)
            if m.duration > duration:

                # There must be a little time after the cut but before the end
                # of this turn.
                if duration > MAX_MISC_TIME + MIN_CLIP_DURATION:
                    clips.append(random_clip(m, MAX_MISC_TIME))
                    duration -= MAX_MISC_TIME
                else:
                    clips.append(random_clip(m, duration))
                    duration = 0
            else:
                if m.duration > MAX_MISC_TIME:
                    clips.append(random_clip(m, MAX_MISC_TIME))
                    duration -= MAX_MISC_TIME
                else:
                    clips.append(m)
                    duration -= m.duration
    if len(clips) > 0:
        out = concatenate_videoclips(clips)
        return out, duration
    else:
        return None, None


def generate_resource_mapping(base):
    resources_dirs = [d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d))]

    resources = {}
    for resource in resources_dirs:
        video_paths = os.listdir(os.path.join(base, resource))
        clips = [VideoFileClip(os.path.join(base, resource, v))
                 for v in video_paths]
        clips.sort(key=lambda v: v.duration, reverse=True)
        resources[resource] = clips
    return resources


def has_spoken_recently(prior_turns, speaker):
    # TODO this does not account for speakers who were skipped
    recent_turns = prior_turns[-RECENT_SPEAKER_THRESHOLD:]
    recent_speakers = [turn_speaker(t) for t in recent_turns]
    return speaker in recent_speakers


def is_short(turn):
    duration = turn_duration(turn)
    if duration < MIN_CLIP_DURATION:
        return True
    return False


def turn_duration(turn):
    start_time = float(turn["start"])
    end_time = float(turn["stop"])
    return end_time - start_time


def same_speaker(turn, speaker):
    return turn_speaker(turn) == speaker


def turn_speaker(turn):
    return turn["speaker"]["name"]


def build_video(resources, transcript, audio):
    sections = transcript["sections"]

    current_remainder = 0
    unknown_mapping = {}
    speaker_videos = []
    for section in sections:
        turns = section["turns"]
        turn_num = 0
        while turn_num < len(turns):
            turn = turns[turn_num]
            name = turn_speaker(turn)

            if name not in JUSTICE_MAPPING:
                assert(turn["speaker"]["roles"] is None)
                if name not in unknown_mapping.keys():
                    n = len(unknown_mapping.keys()) % 2
                    resource = "lawyer" + str(n)
                    unknown_mapping[name] = resource
                else:
                    resource = unknown_mapping[name]
            else:
                resource = JUSTICE_MAPPING[name]

            duration = turn_duration(turn)

            # Just skip very short turns
            if duration < 0.001:
                turn_num += 1
                continue

            if len(turns) > turn_num+2 and \
                    is_short(turns[turn_num+1]) and \
                    has_spoken_recently(turns[:turn_num+1],
                                        turn_speaker(turns[turn_num+1])) and \
                    same_speaker(turns[turn_num+2], name):
                duration += turn_duration(turns[turn_num+1])
                duration += turn_duration(turns[turn_num+2])
                turn_num += 2

            vid, remainder = generate_video_for_speaker(resource,
                                                        duration + current_remainder,
                                                        resources, no_skip=True)
            if vid is None:
                current_remainder = duration
                turn_num += 1
                continue
            else:
                current_remainder = remainder

            speaker_videos.append(vid)
            turn_num += 1

    out = concatenate_videoclips(speaker_videos)
    out.audio = audio.audio
    return out


def main():
    # For reproducible random choices
    random.seed(1)
    resources = generate_resource_mapping("resources")

    url = "https://api.oyez.org/case_media/oral_argument_audio/24097"
    response = urllib.request.urlopen(url)
    data = response.read()
    text = data.decode('utf-8')
    js = json.loads(text)

    subtitle = js["title"]

    transcript = js["transcript"]
    title = transcript["title"]

    print("  {}: \n  {}".format(title, subtitle))

    url = js["media_file"][0]["href"]
    print("Downloading audio from: {}".format(url))

    audio_path = urllib.request.urlretrieve(url)[0]
    audio = VideoFileClip(audio_path)

    video = build_video(resources, transcript, audio)

    print(video.duration, audio.duration)
    video.write_videofile("test.mp4")

if __name__ == "__main__":
    main()
