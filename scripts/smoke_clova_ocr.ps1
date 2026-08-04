$ErrorActionPreference = "Stop"

$requiredVariables = @(
    "FOWOCO_INTERNAL_API_TOKEN",
    "OCR_SAMPLE_FILE",
    "OCR_WORKER_DOCUMENT_ID",
    "OCR_WORKER_ID",
    "OCR_COMPANY_ID",
    "OCR_DOCUMENT_TYPE"
)

foreach ($variableName in $requiredVariables) {
    $value = [Environment]::GetEnvironmentVariable($variableName)
    if ([string]::IsNullOrWhiteSpace($value)) {
        [Console]::Error.WriteLine("Missing required environment variable: $variableName")
        exit 2
    }
}

$documentType = $env:OCR_DOCUMENT_TYPE.Trim().ToUpperInvariant()
if ($documentType -notin @("PASSPORT_COPY", "ARC")) {
    [Console]::Error.WriteLine("OCR_DOCUMENT_TYPE must be PASSPORT_COPY or ARC")
    exit 2
}
if (
    $documentType -eq "PASSPORT_COPY" -and
    [string]::IsNullOrWhiteSpace($env:OCR_COUNTRY_CODE)
) {
    [Console]::Error.WriteLine("Missing required environment variable: OCR_COUNTRY_CODE")
    exit 2
}

$samplePath = [IO.Path]::GetFullPath($env:OCR_SAMPLE_FILE)
if (-not [IO.File]::Exists($samplePath)) {
    [Console]::Error.WriteLine("OCR_SAMPLE_FILE does not exist")
    exit 2
}

$baseUrl = $env:FOWOCO_AI_BASE_URL
if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    $baseUrl = "http://localhost:8000"
}
$endpoint = "$($baseUrl.TrimEnd('/'))/internal/v1/ocr/worker-documents/$($env:OCR_WORKER_DOCUMENT_ID)"
$requestId = [Guid]::NewGuid().ToString()

Add-Type -AssemblyName System.Net.Http
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [System.Net.Http.HttpClient]::new($handler)
$form = [System.Net.Http.MultipartFormDataContent]::new()
$stream = $null

try {
    $client.DefaultRequestHeaders.Authorization =
        [System.Net.Http.Headers.AuthenticationHeaderValue]::new(
            "Bearer",
            $env:FOWOCO_INTERNAL_API_TOKEN
        )
    $form.Add([System.Net.Http.StringContent]::new($requestId), "request_id")
    $form.Add([System.Net.Http.StringContent]::new($env:OCR_WORKER_ID), "worker_id")
    $form.Add([System.Net.Http.StringContent]::new($env:OCR_COMPANY_ID), "company_id")
    $form.Add([System.Net.Http.StringContent]::new($documentType), "document_type")
    if (-not [string]::IsNullOrWhiteSpace($env:OCR_COUNTRY_CODE)) {
        $form.Add(
            [System.Net.Http.StringContent]::new($env:OCR_COUNTRY_CODE.Trim()),
            "country_code"
        )
    }

    $extension = [IO.Path]::GetExtension($samplePath).ToLowerInvariant()
    $contentType = switch ($extension) {
        ".jpg" { "image/jpeg" }
        ".jpeg" { "image/jpeg" }
        ".png" { "image/png" }
        ".pdf" { "application/pdf" }
        default {
            [Console]::Error.WriteLine("OCR_SAMPLE_FILE must be JPEG, PNG, or PDF")
            exit 2
        }
    }
    $stream = [IO.File]::OpenRead($samplePath)
    $fileContent = [System.Net.Http.StreamContent]::new($stream)
    $fileContent.Headers.ContentType =
        [System.Net.Http.Headers.MediaTypeHeaderValue]::new($contentType)
    $form.Add($fileContent, "file", [IO.Path]::GetFileName($samplePath))

    $response = $client.PostAsync($endpoint, $form).GetAwaiter().GetResult()
    $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    Write-Output "HTTP status: $([int]$response.StatusCode)"
    if (-not $response.IsSuccessStatusCode) {
        exit 1
    }

    $result = $responseBody | ConvertFrom-Json
    Write-Output "ocr_status: $($result.ocr_status)"
    Write-Output "matched_template_id: $($result.matched_template_id)"
    Write-Output "document_side: $($result.document_side)"
    Write-Output "review_reasons: $([string]::Join(',', $result.review_reasons))"
}
finally {
    if ($null -ne $stream) {
        $stream.Dispose()
    }
    $form.Dispose()
    $client.Dispose()
    $handler.Dispose()
}
