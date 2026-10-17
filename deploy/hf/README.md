# Retired Hugging Face deployment

This deployment is unsupported. The former uploader copied local models and
configuration into a public Space repository. The uploader, container build and
startup entry point are disabled; they do not publish files or start services.

Keep training videos, organizer labels, annotations, caches and trained artifacts
local. Use the native service controller to explicitly share the analysis app:

```sh
python scripts/serve.py start --public
```

This exposes the running analysis app through an HTTPS tunnel. It does not upload
the project or training files to a Space. The separate annotation reviewer stays
local. The local machine and tunnel must remain running for access.

For service controls, run `python scripts/serve.py --help`.
