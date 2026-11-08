# Reef Rescue repository context

Start with [AGENTS.md](AGENTS.md) for working rules and [README.md](README.md) for the current system. The authoritative source map is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); measured results are indexed in [docs/EVIDENCE.md](docs/EVIDENCE.md).

The active browser pipeline uses Gemma `gemma-4-E4B-it` on Modal, native NVIDIA cuOpt on Modal, a local mission policy and bounded Google `gemini-4-argon` assistance. Gemma describes rendered camera appearance; registry inputs establish eligibility. Argon assistance is limited to rescan/hold/abort. Local controls enforce motion and mechanical verification.

The Python packages at the root implement a separate research path; their default Gemma model and adapters must not be confused with browser deployment. See module READMEs before modifying them. No secret belongs in source or recorded evidence.
