# Configuration
$Url = "https://pardallgames.com"
$OutputFolder = ".\goldeneye_images"
$ZipFile = ".\goldeneye_assets.zip"

# 1. Clear out old files if they exist
if (Test-Path $OutputFolder) { Remove-Item -Recurse -Force $OutputFolder }
if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }
New-Item -ItemType Directory -Path $OutputFolder | Out-Null

Write-Host "Fetching web page data..." -ForegroundColor Cyan

# 2. Get the HTML content from the website
try {
    $Html = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
} catch {
    Write-Error "Failed to download the webpage. Please verify your internet connection."
    return
}

# 3. Extract the image source links using Regular Expressions (No external modules required)
Write-Host "Extracting asset paths..." -ForegroundColor Cyan
$ImageMatches = [regex]::Matches($Html.Content, 'src="([^"\s>]+)"|data-src="([^"\s>]+)"')

$DownloadedCount = 0

foreach ($Match in $ImageMatches) {
    # Extract the clean image URL from the match groups
    $ImgUrl = $Match.Groups[1].Value
    if ([string]::IsNullOrEmpty($ImgUrl)) { $ImgUrl = $Match.Groups[2].Value }
    if ([string]::IsNullOrEmpty($ImgUrl)) { continue }

    # Handle relative URLs cleanly
    if ($ImgUrl.StartsWith("/")) {
        $ImgUrl = "https://library.pardallgames.com" + $ImgUrl
    } elseif (-not $ImgUrl.StartsWith("http")) {
        $ImgUrl = "https://pardallgames.com" + $ImgUrl
    }

    # Format file naming structures cleanly
    $FileName = [System.IO.Path]::GetFileName([System.Uri]$ImgUrl).AbsolutePath
    if ([string]::IsNullOrEmpty($FileName) -or $FileName -eq "/") {
        $FileName = "image_$($DownloadedCount + 1).png"
    }

    $LocalPath = Join-Path $OutputFolder $FileName

    # 4. Download individual image file streams
    try {
        Write-Host "Downloading: $ImgUrl" -ForegroundColor Yellow
        Invoke-WebRequest -Uri $ImgUrl -OutFile $LocalPath -UseBasicParsing -TimeoutSec 10
        $DownloadedCount++
    } catch {
        Write-Host "Skipped an unreadable asset link." -ForegroundColor Gray
    }
}

# 5. Pack everything cleanly into a standard compressed ZIP file
if ($DownloadedCount -gt 0) {
    Write-Host "`nCompression sequence starting..." -ForegroundColor Cyan
    Compress-Archive -Path "$OutputFolder\*" -DestinationPath $ZipFile -Force
    Write-Host "Successfully generated archive file at: $ZipFile" -ForegroundColor Green
    Write-Host "Downloaded total: $DownloadedCount assets." -ForegroundColor Green
} else {
    Write-Host "No image links were discovered on this page." -ForegroundColor Red
}
