FROM mambaorg/micromamba:1.5.10

WORKDIR /workspace

# Mirror GitHub Actions: conda env from solidworks_mcp.yml, then editable install.
COPY solidworks_mcp.yml /tmp/solidworks_mcp.yml
RUN micromamba create -y -n solidworks_mcp -f /tmp/solidworks_mcp.yml \
    && micromamba install -y -n solidworks_mcp -c conda-forge make \
    && micromamba clean --all --yes

COPY . /workspace
RUN micromamba run -n solidworks_mcp pip install -e ".[dev,docs,ui]"

CMD ["bash", "-lc", "micromamba run -n solidworks_mcp make test"]
