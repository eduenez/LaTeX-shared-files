# Dockerfile for LaTeX Codespace
# Uses the full TeX Live distribution with additional tools for linting/formatting.

FROM qmcgaw/latexdevcontainer:latest-full

# Install additional packages needed by the toolchain
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
      git \
      fontconfig \
      make \
      python3 \
      python3-pip \
      cpanminus \
    && cpanm --notest Log::Log4perl Log::Dispatch::File YAML::Tiny File::HomeDir Unicode::GCString \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
