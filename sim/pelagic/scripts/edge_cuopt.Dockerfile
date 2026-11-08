# Supply the compatible pinned CUDA image recorded in edge evidence.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY edge_cuopt_requirements.txt /tmp/edge_cuopt_requirements.txt
RUN python -m venv /opt/edge-cuopt && /opt/edge-cuopt/bin/python -m pip install --extra-index-url https://pypi.nvidia.com -r /tmp/edge_cuopt_requirements.txt && /opt/edge-cuopt/bin/python -m pip check
ENTRYPOINT ["/opt/edge-cuopt/bin/python", "/edge/edge_cuopt_server.py"]
