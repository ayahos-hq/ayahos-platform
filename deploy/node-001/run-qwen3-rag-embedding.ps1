# Dedicated free embedding worker on physical Node 001 (Windows).
# Uses CPU-only llama.cpp on loopback, never shares the chat/GPU llama-swap port.
# It does NOT expose a public endpoint or change Render inference settings.
param(
    [switch]$TestOnly,
    [ValidateRange(1024, 65535)]
    [int]$Port = 8092
)
$ErrorActionPreference = "Stop"
$ModelName = "Qwen3-Embedding-0.6B-Q8_0"
$ModelFile = Join-Path $env:USERPROFILE "models\Qwen3-Embedding-0.6B-Q8_0.gguf"
$ExpectedBytes = 639150592
$ExpectedSha256 = "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"
$Server = Join-Path $env:USERPROFILE "llama.cpp\llama-server.exe"
$Uri = "http://127.0.0.1:$Port"
if ($Port -in @(8000, 8080, 8101, 8110)) {
    throw "Refusing a port reserved for another AyahOS process"
}
if (-not (Test-Path $ModelFile) -or (Get-Item $ModelFile).Length -ne $ExpectedBytes) {
    throw "Missing or incorrectly sized official Qwen3 Embedding model; download from Qwen/Qwen3-Embedding-0.6B-GGUF and verify its SHA256"
}
if ((Get-FileHash $ModelFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedSha256) {
    throw "Qwen3 embedding model checksum mismatch"
}
if (-not (Test-Path $Server)) { throw "llama-server.exe not found in local Node 001 installation" }

$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq "127.0.0.1" } | Select-Object -First 1
if ($listener) {
    $running = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    $HasCpuFlag = $running.CommandLine -match '(?:^|\s)(?:-ngl|--n-gpu-layers)\s+0(?:\s|$)'
    if ($running.Name -ne "llama-server.exe" -or -not $running.CommandLine.Contains($ModelFile) -or
        -not $running.CommandLine.Contains("--embeddings") -or -not $HasCpuFlag) {
        throw "Embedding port is owned by a different process, model, or GPU-enabled worker"
    }
} elseif ($TestOnly) {
    throw "Local embedding worker is not running"
} else {
    $ArgsList = @(
        "-m", $ModelFile, "--host", "127.0.0.1", "--port", "$Port",
        "--embeddings", "--pooling", "last", "-ngl", "0",
        "--ctx-size", "2048", "--no-webui"
    )
    $process = Start-Process -FilePath $Server -ArgumentList $ArgsList -WindowStyle Hidden -PassThru
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if ($process.HasExited) { throw "CPU embedding worker exited during startup" }
        try {
            $health = Invoke-RestMethod -Uri "$Uri/health" -TimeoutSec 2
            if ($health.status -eq "ok") { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw "Embedding worker failed its bounded startup health check" }
}
$models = Invoke-RestMethod -Uri "$Uri/v1/models" -TimeoutSec 5
if (@($models.data | ForEach-Object { $_.id }) -notcontains $ModelName -and
    @($models.data | ForEach-Object { $_.id }) -notcontains $ModelFile) {
    throw "Serving a different embedding model than the SHA256-pinned weights"
}
$body = @{model=$ModelName;input=@(
    "Undermind enforces policy and permissions.",
    "The weather is sunny today."
)} | ConvertTo-Json -Compress
$watch = [Diagnostics.Stopwatch]::StartNew()
$result = Invoke-RestMethod -Uri "$Uri/v1/embeddings" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 60
$watch.Stop()
if (@($result.data).Count -ne 2) { throw "Embedding endpoint returned an unexpected batch size" }
foreach ($row in $result.data) {
    $vector = @($row.embedding)
    if ($vector.Count -ne 1024) { throw "Expected exactly 1024 embedding dimensions" }
    if (-not @($vector | Where-Object { [double]$_ -ne 0 } | Select-Object -First 1).Count) {
        throw "Embedding model returned an all-zero vector"
    }
}
[pscustomobject]@{
    schema = "ayahos-node-rag-embedding-proof/v1"
    model = $ModelName
    model_sha256 = $ExpectedSha256
    dimensions = 1024
    vectors = 2
    cpu_only = $true
    local_only = $true
    endpoint = "$Uri/v1/embeddings"
    latency_ms = [math]::Round($watch.Elapsed.TotalMilliseconds, 1)
    verified_utc = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json -Compress
