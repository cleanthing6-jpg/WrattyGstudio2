# Gbedu

**Gbedu** — AI afrobeats beat maker engine.

Sing or upload a vocal, get a beat in the SAME key + tempo that goes WITH
your song. No melody copying. No mimicry.

## Name
Yoruba / Nigerian Pidgin: *gbedu* = a heavy, groovy beat.

## Architecture
  client (app / termux)  ->  Gbedu engine (librosa + ACE-Step)  ->  beat.wav

## Engine
  backend/analyze.py    vocal -> BPM + key
  backend/generate.py   conditions -> beat (ACE-Step)

## Status
scaffold — analysis untested, generation not wired
