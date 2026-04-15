# Playwright official image — pinned to v1.39.0-jammy.
#
# Why 1.39.0 specifically:
#   - The Playwright driver bundles its own Node runtime (at
#     /usr/local/lib/python3.10/dist-packages/playwright/driver/node).
#   - Playwright 1.39.x bundles Node v18.18.0 (the last LTS-18 line).
#   - Playwright 1.40+ switched the bundled driver to Node 20.
#   - Therefore 1.39.0 is the known-good Node-18 Playwright release.
#
# The Python wheel version in requirements.txt MUST match this tag
# exactly (1.39.0) so the driver and browser binaries align.
FROM mcr.microsoft.com/playwright/python:v1.39.0-jammy

WORKDIR /e2e

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify the bundled driver Node runtime is v18.x (fails the build
# loudly if the Playwright pin ever drifts to a non-Node-18 version).
RUN /usr/local/lib/python3.10/dist-packages/playwright/driver/node --version \
    | grep -E '^v18\.' \
    || (echo "ERROR: expected bundled Node 18.x, got $(/usr/local/lib/python3.10/dist-packages/playwright/driver/node --version)" && exit 1)

COPY . /e2e

CMD ["python", "-m", "pytest", "/e2e/tests", "-v", "--tb=short"]
