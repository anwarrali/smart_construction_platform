param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$presentationRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $presentationRoot "dist"
$indexFile = Join-Path $distRoot "index.html"
$serverPort = 4173
$presentationUrl = "http://127.0.0.1:$serverPort/"

if (-not (Test-Path -LiteralPath $indexFile)) {
    throw "The production build is missing. Run npm run build once, then open this launcher again."
}

$mimeTypes = @{
    ".html" = "text/html; charset=utf-8"
    ".css"  = "text/css; charset=utf-8"
    ".js"   = "text/javascript; charset=utf-8"
    ".svg"  = "image/svg+xml"
    ".png"  = "image/png"
    ".jpg"  = "image/jpeg"
    ".jpeg" = "image/jpeg"
    ".ico"  = "image/x-icon"
    ".json" = "application/json; charset=utf-8"
    ".woff" = "font/woff"
    ".woff2" = "font/woff2"
}

$listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback,
    $serverPort
)

try {
    $listener.Start()
} catch {
    Write-Host "Port $serverPort is already in use." -ForegroundColor Yellow
    Write-Host "Opening the existing local presentation server..."
    Start-Process $presentationUrl
    exit 0
}

Write-Host ""
Write-Host "  SMART CONSTRUCTION MANAGEMENT PLATFORM" -ForegroundColor Cyan
Write-Host "  Presentation: $presentationUrl"
Write-Host "  Keep this window open while presenting."
Write-Host "  Close this window to stop the local server."
Write-Host ""

if (-not $NoBrowser) {
    Start-Process $presentationUrl
}

try {
    while ($true) {
        $client = $listener.AcceptTcpClient()
        try {
            $stream = $client.GetStream()
            $reader = [System.IO.StreamReader]::new(
                $stream,
                [System.Text.Encoding]::ASCII,
                $false,
                1024,
                $true
            )

            $requestLine = $reader.ReadLine()
            if ([string]::IsNullOrWhiteSpace($requestLine)) {
                continue
            }

            while (-not [string]::IsNullOrEmpty($reader.ReadLine())) {
                # Consume the remaining request headers.
            }

            $requestTarget = ($requestLine -split " ")[1]
            $requestPath = [System.Uri]::UnescapeDataString(
                ($requestTarget -split "\?")[0]
            ).TrimStart("/")

            if ([string]::IsNullOrWhiteSpace($requestPath)) {
                $requestPath = "index.html"
            }

            $candidatePath = [System.IO.Path]::GetFullPath(
                (Join-Path $distRoot $requestPath)
            )
            $resolvedDistRoot = [System.IO.Path]::GetFullPath($distRoot)

            if (-not $candidatePath.StartsWith(
                $resolvedDistRoot,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                $candidatePath = $indexFile
            }

            if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
                $candidatePath = $indexFile
            }

            $body = [System.IO.File]::ReadAllBytes($candidatePath)
            $extension = [System.IO.Path]::GetExtension($candidatePath).ToLowerInvariant()
            $contentType = if ($mimeTypes.ContainsKey($extension)) {
                $mimeTypes[$extension]
            } else {
                "application/octet-stream"
            }

            $headers = (
                "HTTP/1.1 200 OK`r`n" +
                "Content-Type: $contentType`r`n" +
                "Content-Length: $($body.Length)`r`n" +
                "Cache-Control: no-cache`r`n" +
                "Connection: close`r`n`r`n"
            )

            $headerBytes = [System.Text.Encoding]::ASCII.GetBytes($headers)
            $stream.Write($headerBytes, 0, $headerBytes.Length)
            $stream.Write($body, 0, $body.Length)
            $stream.Flush()
        } finally {
            $client.Dispose()
        }
    }
} finally {
    $listener.Stop()
}
