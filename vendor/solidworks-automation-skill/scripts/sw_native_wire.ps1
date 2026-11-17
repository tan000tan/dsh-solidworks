<# @brief 通过 UTF-8 标准输入接收严格 JSON；保留短 Base64 调用的兼容入口。 #>
param([string]$InputBase64,[Parameter(Mandatory=$true)][string]$InteropRoot)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
$request=if($InputBase64){[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($InputBase64))}else{[Console]::In.ReadToEnd()}
if([string]::IsNullOrWhiteSpace($request)-or [Text.Encoding]::UTF8.GetByteCount($request)-gt 1048576){throw 'Native request must contain 1..1048576 UTF-8 bytes'}
$dll=Join-Path $InteropRoot 'SolidWorks.Interop.sldworks.dll'
$constants=Join-Path $InteropRoot 'SolidWorks.Interop.swconst.dll'
Add-Type -Path $dll
Add-Type -Path $constants
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'sw_native_wire.cs'))) -ReferencedAssemblies @($dll,$constants,'System.Web.Extensions','System.Core')
[NativeWireTools]::Run($request)
