param([string]$BaseUrl = "http://localhost:8000/api/v1")

$ErrorActionPreference = "Stop"
function Login([string]$email, [string]$password = "password123") {
  $body = "username=$([uri]::EscapeDataString($email))&password=$([uri]::EscapeDataString($password))"
  (Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $body).access_token
}
function Headers([string]$token) { @{ Authorization = "Bearer $token" } }
function Api([string]$method, [string]$path, $body, [string]$token) {
  $args = @{ Method=$method; Uri="$BaseUrl$path"; Headers=(Headers $token) }
  if ($null -ne $body) { $args.ContentType="application/json"; $args.Body=($body | ConvertTo-Json -Depth 15) }
  Invoke-RestMethod @args
}
function ExpectStatus([int[]]$statuses, [string]$method, [string]$path, $body, [string]$token) {
  try { Api $method $path $body $token | Out-Null; throw "Expected HTTP $($statuses -join '/') for $method $path" }
  catch {
    $actual = [int]$_.Exception.Response.StatusCode
    if ($actual -notin $statuses) { throw "Expected HTTP $($statuses -join '/'), received $actual for $method $path. $($_.Exception.Message)" }
  }
}
function Assert($condition, [string]$message) { if (-not $condition) { throw "ASSERTION FAILED: $message" } }
function Items($value) { if ($value -is [array]) { @($value) } elseif ($null -eq $value) { @() } else { @($value) } }

$run = [guid]::NewGuid().ToString("N").Substring(0, 8)
$admin = Login "admin@constro.io"
$pm = Login "pm@constro.io"
$civilEngineer = Login "civil@constro.io"
$consultant = Login "consultant@constro.io"
$users = Items (Api Get "/users" $null $admin)
$civil = $users | Where-Object email -eq "civil@constro.io" | Select-Object -First 1
$electrical = $users | Where-Object email -eq "elec@constro.io" | Select-Object -First 1
$consultantUser = $users | Where-Object email -eq "consultant@constro.io" | Select-Object -First 1
Assert ($civil -and $electrical -and $consultantUser) "Required existing users are missing"
Assert ($consultantUser.role -eq "engineer" -and $consultantUser.engineerAffiliation -eq "external_consultant" -and $consultantUser.engineerProfile.discipline -eq "civil") "Consultant identity is not unified Engineer + external_consultant + Civil"
$restoreElectricalInactive = $electrical.status -ne "active"
if ($restoreElectricalInactive) { Api Put "/users/$($electrical.id)/activate" $null $admin | Out-Null }
$electricalEngineer = Login "elec@constro.io"

$project = (Api Get "/projects?limit=100" $null $pm).data | Select-Object -First 1
Assert $project "No existing Project Manager project is available"
$tasksToDelete = @()
$attachmentsToDelete = @()
$checks = [ordered]@{}
$pngPath = Join-Path $env:TEMP "consultant-$run.png"
try {
  [IO.File]::WriteAllBytes($pngPath, [byte[]](0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,0x00,0x00,0x00,0x00))
  $projects = (Api Get "/projects?limit=100" $null $consultant).data
  Assert ($projects.id -contains $project.id) "Consultant cannot see assigned project"
  $dashboard = Api Get "/consultant/projects/$($project.id)/dashboard" $null $consultant
  Assert ($dashboard.specialization -eq "civil" -and $dashboard.project.id -eq $project.id) "Consultant dashboard is not project/specialization scoped"
  ExpectStatus @(403) Get "/users" $null $consultant
  ExpectStatus @(403) Get "/projects/$($project.id)/members" $null $consultant
  ExpectStatus @(403) Post "/projects" @{name="Forbidden"} $consultant
  $checks.login_project_scope_rbac = $true

  $gate = Api Post "/tasks" @{ projectId=$project.id; name="Consultant gate $run"; description="Civil work requiring inspection"; discipline="civil"; status="todo"; priority="critical"; assigneeIds=@($civil.id); reviewRequired=$true; reviewDueDate=(Get-Date).ToString("yyyy-MM-dd") } $pm
  $tasksToDelete += $gate.id
  $dependent = Api Post "/tasks" @{ projectId=$project.id; name="Dependent pour $run"; discipline="civil"; status="todo"; priority="high"; assigneeIds=@($civil.id); reviewRequired=$false; dependencyIds=@($gate.id) } $pm
  $tasksToDelete += $dependent.id
  $parallel = Api Post "/tasks" @{ projectId=$project.id; name="Parallel internal $run"; discipline="civil"; status="todo"; priority="medium"; assigneeIds=@($civil.id); reviewRequired=$false } $pm
  $tasksToDelete += $parallel.id
  $electricalTask = Api Post "/tasks" @{ projectId=$project.id; name="Electrical inspection $run"; discipline="electrical"; status="todo"; priority="high"; assigneeIds=@($electrical.id); reviewRequired=$true } $pm
  $tasksToDelete += $electricalTask.id
  Assert ($gate.reviewRequired -and -not $parallel.reviewRequired) "Per-task review requirement was not stored"

  Api Put "/tasks/$($gate.id)/start" $null $civilEngineer | Out-Null
  Api Put "/tasks/$($gate.id)/progress" @{progressPercentage=100;note="Civil execution completed"} $civilEngineer | Out-Null
  $evidence = Invoke-RestMethod -Method Post -Uri "$BaseUrl/attachments/upload" -Headers (Headers $civilEngineer) -Form @{file=Get-Item $pngPath;project_id=$project.id;entity_type="TASK";entity_id=$gate.id}
  $attachmentsToDelete += $evidence.id
  $gate = Api Put "/tasks/$($gate.id)/submit-review" @{completionNote="Reinforcement checked against approved drawing"} $civilEngineer
  Assert ($gate.status -eq "under_review" -and $gate.reviewStatus -eq "pending") "Contractor submission did not enter Under Review"
  ExpectStatus @(400,409) Put "/tasks/$($gate.id)/submit-review" @{} $civilEngineer
  ExpectStatus @(400) Put "/tasks/$($dependent.id)/start" $null $civilEngineer
  $parallel = Api Put "/tasks/$($parallel.id)/start" $null $civilEngineer
  Assert ($parallel.status -eq "in_progress") "Unrelated parallel task was incorrectly frozen"
  Api Put "/tasks/$($parallel.id)/progress" @{progressPercentage=100} $civilEngineer | Out-Null
  $parallel = Api Put "/tasks/$($parallel.id)/complete-execution" $null $civilEngineer
  Assert ($parallel.status -eq "done" -and -not $parallel.reviewStatus) "Internal task was not completed without fake Consultant approval"
  ExpectStatus @(400) Put "/tasks/$($parallel.id)/submit-review" @{} $civilEngineer
  $checks.submission_and_approval_gate = $true

  $pending = Items (Api Get "/consultant/projects/$($project.id)/reviews" $null $consultant)
  $review = $pending | Where-Object taskId -eq $gate.id | Select-Object -First 1
  Assert ($review -and $review.evidenceCount -eq 1 -and $review.dependentTasksBlocked -ge 1) "Pending review/evidence/dependency impact is incomplete"
  $detail = Api Get "/consultant/projects/$($project.id)/reviews/$($review.id)" $null $consultant
  Assert ($detail.submissionEvidence.Count -eq 1 -and $detail.review.completionNote -match "Reinforcement") "Submission evidence snapshot or completion note missing"
  Api Put "/tasks/$($gate.id)/start-review" $null $consultant | Out-Null
  $reviewAttachment = Invoke-RestMethod -Method Post -Uri "$BaseUrl/attachments/upload" -Headers (Headers $consultant) -Form @{file=Get-Item $pngPath;project_id=$project.id;entity_type="TASK_REVIEW";entity_id=$review.id}
  $attachmentsToDelete += $reviewAttachment.id
  Api Post "/tasks/$($gate.id)/comments" @{content="[Consultant Review] Verify bar spacing at grid B4."} $consultant | Out-Null
  $clarification = Api Put "/tasks/$($gate.id)/request-clarification" @{question="Confirm the approved drawing revision used."} $consultant
  Assert ($clarification.status -eq "clarification_requested") "Clarification was not recorded"
  $gateAfterClarification = Api Get "/tasks/$($gate.id)" $null $civilEngineer
  Assert ($gateAfterClarification.status -eq "under_review") "Clarification incorrectly changed task state"
  $response = Api Put "/tasks/$($gate.id)/respond-clarification" @{response="Drawing revision C-04 was used and is attached."} $civilEngineer
  Assert ($response.status -eq "pending" -and $response.clarificationResponse -match "C-04") "Contractor clarification response was not persisted"
  $checks.review_detail_comment_attachment_clarification = $true

  ExpectStatus @(400) Put "/tasks/$($gate.id)/reject" @{comments="Not acceptable"} $consultant
  $gate = Api Put "/tasks/$($gate.id)/reject" @{comments="Spacing differs from drawing";rejectionReason="Non-compliant reinforcement spacing";requiredCorrections="Correct spacing and upload new evidence"} $consultant
  Assert ($gate.status -eq "rework_required" -and $gate.reviewStatus -eq "rejected") "Rejection did not create Rework Required"
  ExpectStatus @(400) Put "/tasks/$($dependent.id)/start" $null $civilEngineer
  $history = Items (Api Get "/consultant/projects/$($project.id)/history" $null $consultant)
  Assert (($history | Where-Object taskId -eq $gate.id).requiredCorrections -match "Correct spacing") "Rejection correction history missing"
  Api Put "/tasks/$($gate.id)/start-rework" $null $civilEngineer | Out-Null
  Api Put "/tasks/$($gate.id)/submit-review" @{completionNote="Spacing corrected per C-04"} $civilEngineer | Out-Null
  $reviews = Items (Api Get "/tasks/$($gate.id)/reviews" $null $civilEngineer)
  Assert ($reviews.Count -eq 2 -and ($reviews.submissionNumber -contains 1) -and ($reviews.submissionNumber -contains 2)) "Review attempt history was overwritten"
  $pending2 = Items (Api Get "/consultant/projects/$($project.id)/reviews" $null $consultant)
  $review2 = $pending2 | Where-Object taskId -eq $gate.id | Select-Object -First 1
  Assert ($review2.submissionNumber -eq 2 -and $review2.isResubmission) "Resubmission was not identified"
  $gate = Api Put "/tasks/$($gate.id)/approve" @{comments="Corrected work complies with drawing C-04"} $consultant
  Assert ($gate.status -eq "done" -and $gate.reviewStatus -eq "approved" -and $gate.reviewedById -eq $consultantUser.id) "Approval did not store final task state/reviewer"
  ExpectStatus @(409) Put "/tasks/$($gate.id)/approve" @{comments="duplicate"} $consultant
  $dependent = Api Put "/tasks/$($dependent.id)/start" $null $civilEngineer
  Assert ($dependent.status -eq "in_progress") "Eligible dependent task did not unlock after approval"
  $checks.rejection_resubmission_approval_concurrency = $true

  Api Put "/tasks/$($electricalTask.id)/start" $null $electricalEngineer | Out-Null
  Api Put "/tasks/$($electricalTask.id)/progress" @{progressPercentage=100} $electricalEngineer | Out-Null
  Api Put "/tasks/$($electricalTask.id)/submit-review" @{completionNote="Electrical evidence"} $electricalEngineer | Out-Null
  $civilPending = Items (Api Get "/consultant/projects/$($project.id)/reviews" $null $consultant)
  Assert ($civilPending.taskId -notcontains $electricalTask.id) "Electrical submission leaked to Civil Consultant"
  ExpectStatus @(403) Get "/tasks/$($electricalTask.id)" $null $consultant
  ExpectStatus @(403) Put "/tasks/$($electricalTask.id)/approve" @{comments="forbidden"} $consultant
  ExpectStatus @(403) Put "/tasks/$($gate.id)/progress" @{progressPercentage=50} $consultant
  ExpectStatus @(403) Post "/tasks" @{projectId=$project.id;name="Consultant execution task";discipline="civil";priority="low"} $consultant
  $checks.specialization_and_execution_separation = $true

  $consultantDashboard = Api Get "/consultant/projects/$($project.id)/dashboard" $null $consultant
  Assert ($consultantDashboard.stats.approvedThisWeek -ge 1) "Consultant dashboard did not refresh after approval"
  $consultantNotifications = Api Get "/notifications?project_id=$($project.id)&limit=100" $null $consultant
  $engineerNotifications = Api Get "/notifications?project_id=$($project.id)&limit=100" $null $civilEngineer
  Assert ($consultantNotifications.items.Count -gt 0 -and $engineerNotifications.items.Count -gt 0) "Internal review notifications are missing"
  Assert ((Api Get "/projects?limit=5" $null $admin).data.Count -gt 0) "Administrator regression check failed"
  Assert ((Api Get "/projects?limit=5" $null $pm).data.Count -gt 0) "Project Manager regression check failed"
  Assert ((Api Get "/dashboard/engineer/projects/$($project.id)" $null $civilEngineer).project.id -eq $project.id) "Main Contractor Engineer regression check failed"
  $checks.dashboard_notifications_regressions = $true

  [pscustomobject]@{Status="PASS";Run=$run;ProjectId=$project.id;Checks=$checks} | ConvertTo-Json -Depth 8
}
finally {
  foreach ($attachmentId in $attachmentsToDelete) {
    try { Api Delete "/attachments/$attachmentId" $null $pm | Out-Null }
    catch { Write-Warning "Could not remove test attachment $attachmentId`: $($_.Exception.Message)" }
  }
  [object[]]$cleanupTaskIds = @($tasksToDelete | Select-Object -Unique)
  [array]::Reverse($cleanupTaskIds)
  foreach ($taskId in $cleanupTaskIds) {
    try { Api Delete "/tasks/$taskId" $null $pm | Out-Null }
    catch { Write-Warning "Could not remove test task $taskId`: $($_.Exception.Message)" }
  }
  Remove-Item -LiteralPath $pngPath -ErrorAction SilentlyContinue
  if ($restoreElectricalInactive) { try { Api Put "/users/$($electrical.id)/deactivate" $null $admin | Out-Null } catch {} }
}
