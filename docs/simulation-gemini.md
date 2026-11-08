# Optional Gemini image review

> **Separate research adapter; not the current browser model pipeline.** This
> document describes the optional Python image-review CLI. The current browser
> uses Gemma E4B on Modal and bounded Argon assistance; see the
> [project README](../README.md) and [architecture](ARCHITECTURE.md).
> Historical validation notes below apply only to this adapter.

The Python research simulation runs offline with labelled fixture perception. `perception/gemini_client.py` is a separate, opt-in cloud
adapter implementing the team's `VisionLLM.ask(prompt, image_png, json_schema)`
contract and returning `GemmaReply`. It is not imported by the offline runner.

The default model is `gemini-3.5-flash-lite`, listed by Google as a low-cost
multimodal model with image input and structured output. The adapter uses the
official Google Gen AI SDK's Interactions API. Documentation checked November 7,
2026: [model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite),
[Interactions overview](https://ai.google.dev/gemini-api/docs/interactions-overview),
[structured output format](https://ai.google.dev/gemini-api/docs/interactions-breaking-changes-may-2026).

## Review one saved PNG

Install `google-genai>=2.33.0` in your environment (offline transport tests ran
against 2.33.0). Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` through your usual secret
manager or shell environment. The adapter never reads `.env` files. From the
repository root, explicitly opt in to sending **that frame** to Google:

```sh
python -m perception.gemini_client /absolute/path/frame.png --allow-remote --out /absolute/path/review.json
```

Optional arguments: `--model`, `--prompt`, and `--schema /absolute/path/schema.json`.
The report contains `source: gemini_cloud`, model, input image hash, interaction
ID, actual response text, latency and provider-reported token usage. No live API
call was made during implementation: tests use mock responses and an offline SDK
HTTP transport. Credentials, billing and model availability remain unverified.

For Python integration:

```python
from pathlib import Path
from perception.gemini_client import GeminiClient

client = GeminiClient(allow_remote=True, max_output_tokens=1024, timeout_s=30)
try:
    reply = client.ask("Describe visible reef and gripper artifacts.", Path("frame.png").read_bytes())
    print(reply.text, reply.usage)
finally:
    client.close()
```

`run_mission` also requires `allow_remote_perception=True` if this client is
explicitly supplied there. Do not enable it for offline recordings. The model
is advisory perception, not a source of genotype truth or evidence that tissue
has recovered. Pairing, fragment identity, motion and push-test outcomes stay in
the team's deterministic mission and simulator code.

## Bounds and failure behavior

One PNG per ask; at most 8 MiB and 16 megapixels, resized to a 768-pixel longest
side. Prompts are limited to 12,000 characters. Output requests default to 1,024
tokens (configurable up to 4,096), with minimal thinking. Calls use a 30-second
per-request HTTP timeout (configurable up to 120), a minimal SDK retry budget,
and no application retries, streaming, tools, background tasks or interaction
storage (`store=False`). SDK retry semantics can vary by version; timeout is
per attempt, not a guaranteed whole-operation deadline. Provider-reported usage
is logged, including unsuccessful/empty completed responses when returned.

Missing credentials, request errors, incomplete/empty output, and invalid JSON
are errors. Nothing silently falls back to a fixture or another model. The
provider enforces the supplied JSON schema; callers still validate their own
domain fields. Error logs omit SDK exception bodies to avoid exposing request
data or credentials. `store=False` disables retrievable Interactions history;
it does not assert anything beyond Google's service data policy.