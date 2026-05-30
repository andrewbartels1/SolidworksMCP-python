# syntax=docker/dockerfile:1.4
FROM mambaorg/micromamba:1.5.10

WORKDIR /workspace

# ── Stage 1: conda env ────────────────────────────────────────────────────────
# Rebuilds only when solidworks_mcp.yml changes.
# Cache mount keeps downloaded conda packages across builds.
COPY --chown=mambauser:mambauser solidworks_mcp.yml /tmp/solidworks_mcp.yml
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=1000,gid=1000 \
    micromamba create -y -n solidworks_mcp -f /tmp/solidworks_mcp.yml \
    && micromamba install -y -n solidworks_mcp -c conda-forge make \
    && micromamba clean --all --yes

# ── Stage 2: pip install ──────────────────────────────────────────────────────
# Rebuilds only when pyproject.toml or src/ changes.
# Cache mount avoids re-downloading wheels on dep bumps.
# Skips `docs` extras — MkDocs/Sphinx are not needed to run tests.
COPY --chown=mambauser:mambauser pyproject.toml /workspace/
COPY --chown=mambauser:mambauser src/ /workspace/src/
RUN --mount=type=cache,target=/home/mambauser/.cache/pip,uid=1000,gid=1000 \
    micromamba run -n solidworks_mcp pip install -e ".[dev,test,ui,rag]"

# ── Stage 3: test sources ─────────────────────────────────────────────────────
# Copied last so frequent edits to tests don't bust the pip cache layer.
COPY --chown=mambauser:mambauser . /workspace

CMD ["bash", "-lc", "micromamba run -n solidworks_mcp make test"]
