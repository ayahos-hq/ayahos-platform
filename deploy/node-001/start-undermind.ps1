# Node 1 (local desktop, Windows) — serve the Liquid AI LFM2.5-1.2B-Instruct
# as AyahOS's autonomic (Undermind) critic model.
#
# Run this on the desktop itself. It starts a dedicated llama-server for
# the LFM only, on loopback port 8082, always warm. It deliberately does
# NOT go through the cognitive llama-swap instance: llama-swap evicts the
# loaded model on a swap, and the critic has a short timeout budget, so a
# cold swap would make critic calls time out and be recorded as
# unavailable (telemetry only — never a wrong decision, but useless).
#
# Model file: LiquidAI/LFM2.5-1.2B-Instruct-GGUF,
# LFM2.5-1.2B-Instruct-Q4_K_M.gguf
#   bytes  730895168
#   sha256 b1b3de114215d9507409a662a501a631095a479a419584e8a2ded6304b19b4f5
# License: LFM Open License v1.0 (free commercial use under $10M revenue).
#
# Adjust $ModelDir if the GGUF lives elsewhere.
$ErrorActionPreference = "Stop"
$ModelDir = "C:\Users\Admin\models"
$ModelFile = Join-Path $ModelDir "lfm2.5-1.2b.gguf"

if (-not (Test-Path $ModelFile)) {
    throw "Missing $ModelFile — download LFM2.5-1.2B-Instruct-Q4_K_M.gguf from LiquidAI/LFM2.5-1.2B-Instruct-GGUF and rename it to lfm2.5-1.2b.gguf"
}
$hash = (Get-FileHash $ModelFile -Algorithm SHA256).Hash.ToLower()
if ($hash -ne "b1b3de114215d9507409a662a501a631095a479a419584e8a2ded6304b19b4f5") {
    throw "SHA256 mismatch for $ModelFile (got $hash)"
}

# -ngl 99: the 1.2B Q4_K_M is ~0.73 GB; it fits the RTX 3060's 12 GB VRAM
# alongside the cognitive model with room to spare.
# --alias must match DUAL_LINEAGE_CRITIC_MODEL / the node agent's
# DUAL_LINEAGE_NODE_AUTONOMIC_MODEL exactly: lfm2.5-1.2b
llama-server `
    --host 127.0.0.1 --port 8082 `
    -m $ModelFile `
    --alias lfm2.5-1.2b `
    -ngl 99 -c 8192 --jinja
