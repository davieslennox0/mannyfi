# MannyFi demo video

`mannyfi-demo.mp4` (about 1 minute 40, 1920x1080, with a female voice-over) is a full walkthrough: opening the website, looking inside a basket, getting a wallet, adding the connector, the one-page setup (sign in, passkey, limits), adding USDC, and then a balance check, a purchase and a status check inside the chat.

It is built from the product itself, in the website's own design:

- the website scenes are **real screenshots** of https://mannyfi.xyz (captured by `capture.py`);
- the chat cards are rendered by the **real card renderer** (`../server/sarf/card.py`) with sample numbers (`make_cards.py`);
- the setup, connector and funding scenes are re-drawn in the site's fonts and colours (`demo.html`), because they need a wallet and a passkey to show for real.

The amounts, the account name (`alice.near`) and the order are **samples for illustration**, not a real trade. Not financial advice.

## The voice-over and the sync

The script is in `narration.py`. `tts.py` speaks each line with [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (voice: `af_heart`, a little brisker than normal speech, with a script written to be read aloud), measures how long each line really takes, and writes `timeline.js` and `narration.wav`. The video is driven by those measurements, so everything follows the voice instead of a fixed clock: the caption words are revealed as they are spoken, the question is typed while she says it, each setup step ticks as she finishes it, and each card appears when she describes it.

## Rebuild it

```
cd demo
../server/.venv/bin/python capture.py       # fresh screenshots of the live site
../server/.venv/bin/python make_cards.py    # the sample cards
/path/to/tts-env/bin/python tts.py       # voice and timings (pip install kokoro-onnx soundfile; model files from the kokoro-onnx releases page, see tts.py)
../server/.venv/bin/python render.py video 24   # renders at 1080p and streams the frames into ffmpeg, writing mannyfi-demo.mp4 with the voice (needs chromium and ffmpeg)
```

`render.py preview 5 30 60` saves single frames at those seconds so you can check a scene quickly.
