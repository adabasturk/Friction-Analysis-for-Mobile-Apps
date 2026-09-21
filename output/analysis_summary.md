# Mobile Apps: Funnel Friction Analysis — Bulgular

Estimation frame: 596 records (in_estimation_frame=1, validation_status='valid').
Every cell with n < 30 is flagged with ⚠.

## 1. Findings that need no LLM
No sampling error - over all 6,961 substantive records.
- Records dropped by the keyboard-mash filter: **9**
- Cluster 5 (n=630, avg rating 1.60 - gold mine): n=630, avg rating=1.60
  - Retake AI: 206 (33%)
  - Nova: 186 (30%)
  - Chat AI: 158 (25%)
  - ReShoot: 80 (13%)
- Cluster 10 (n=367 - face-editor cluster): n=367, avg rating=3.52
  - Retake AI: 185 (50%)
  - ReShoot: 140 (38%)
  - Chat AI: 24 (7%)
  - Nova: 18 (5%)

**Review volume imbalance (per app):**

- Nova: 3565
- Chat AI: 3368
- Retake AI: 1772
- ReShoot: 727

## 2a. friction_type distribution, within pair
- **chatbot / paywall_timing**: Chat AI %4.3 (n=149) vs Nova %2.5 (n=148) -> not significant (CIs overlap)
- **chatbot / price_level**: Chat AI %2.4 (n=149) vs Nova %2.5 (n=148) -> not significant (CIs overlap)
- **chatbot / subscription_trap**: Chat AI %3.3 (n=149) vs Nova %7.4 (n=148) -> not significant (CIs overlap)
- **chatbot / free_quota_limit**: Chat AI %4.3 (n=149) vs Nova %3.9 (n=148) -> not significant (CIs overlap)
- **chatbot / referral_gate**: Chat AI %0.7 (n=149) vs Nova %0.0 (n=148) -> not significant (CIs overlap)
- **chatbot / quality_gap**: Chat AI %2.5 (n=149) vs Nova %3.6 (n=148) -> not significant (CIs overlap)
- **chatbot / onboarding_confusion**: Chat AI %7.1 (n=149) vs Nova %6.7 (n=148) -> not significant (CIs overlap)
- **chatbot / performance**: Chat AI %0.7 (n=149) vs Nova %4.2 (n=148) -> not significant (CIs overlap)
- **chatbot / none**: Chat AI %74.6 (n=149) vs Nova %69.3 (n=148) -> not significant (CIs overlap)
- **face / paywall_timing**: Retake AI %14.1 (n=150) vs ReShoot %6.3 (n=149) -> significant
- **face / price_level**: Retake AI %9.0 (n=150) vs ReShoot %1.6 (n=149) -> significant
- **face / subscription_trap**: Retake AI %6.1 (n=150) vs ReShoot %4.8 (n=149) -> not significant (CIs overlap)
- **face / free_quota_limit**: Retake AI %9.0 (n=150) vs ReShoot %5.3 (n=149) -> not significant (CIs overlap)
- **face / referral_gate**: Retake AI %1.0 (n=150) vs ReShoot %1.4 (n=149) -> not significant (CIs overlap)
- **face / quality_gap**: Retake AI %4.0 (n=150) vs ReShoot %5.1 (n=149) -> not significant (CIs overlap)
- **face / onboarding_confusion**: Retake AI %6.8 (n=150) vs ReShoot %7.0 (n=149) -> not significant (CIs overlap)
- **face / performance**: Retake AI %1.8 (n=150) vs ReShoot %1.4 (n=149) -> not significant (CIs overlap)
- **face / none**: Retake AI %48.2 (n=150) vs ReShoot %67.1 (n=149) -> significant

## 2b. trigger_moment distribution, within pair
note: 'none' = friction_type='none' (no trigger moment)

- **chatbot / before_first_use**: Chat AI %9.6 (n=149) vs Nova %11.6 (n=148) -> not significant (CIs overlap)
- **chatbot / after_first_result**: Chat AI %9.9 (n=149) vs Nova %6.4 (n=148) -> not significant (CIs overlap)
- **chatbot / after_free_quota**: Chat AI %3.6 (n=149) vs Nova %5.0 (n=148) -> not significant (CIs overlap)
- **chatbot / none**: Chat AI %76.9 (n=149) vs Nova %77.0 (n=148) -> not significant (CIs overlap)
- **face / before_first_use**: Retake AI %29.1 (n=150) vs ReShoot %19.2 (n=149) -> not significant (CIs overlap)
- **face / after_first_result**: Retake AI %8.4 (n=150) vs ReShoot %9.1 (n=149) -> not significant (CIs overlap)
- **face / after_free_quota**: Retake AI %5.1 (n=150) vs ReShoot %3.9 (n=149) -> not significant (CIs overlap)
- **face / none**: Retake AI %57.4 (n=150) vs ReShoot %67.8 (n=149) -> not significant (CIs overlap)

## 2c. would_pay_signal='conditional' - most valuable segment
- **chatbot**: Chat AI %9.2 (n=149) vs Nova %6.0 (n=148) -> not significant (CIs overlap)
- **face**: Retake AI %12.3 (n=150) vs ReShoot %11.9 (n=149) -> not significant (CIs overlap)

Example quotes (discovery frame, NOT a rate, illustration only): 8 records -> conditional_quotes_sample.csv

## 2d. price_level vs free_quota_limit - never combined
- **chatbot / price_level**: Chat AI %2.4 (n=149) vs Nova %2.5 (n=148) -> not significant (CIs overlap)
- **face / price_level**: Retake AI %9.0 (n=150) vs ReShoot %1.6 (n=149) -> significant
- **chatbot / free_quota_limit**: Chat AI %4.3 (n=149) vs Nova %3.9 (n=148) -> not significant (CIs overlap)
- **face / free_quota_limit**: Retake AI %9.0 (n=150) vs ReShoot %5.3 (n=149) -> not significant (CIs overlap)

## 2e. paid_but_still_limited=true rate
- **chatbot**: Chat AI %6.7 (n=149) vs Nova %6.0 (n=148) -> not significant (CIs overlap)
- **face**: Retake AI %13.2 (n=150) vs ReShoot %10.7 (n=149) -> not significant (CIs overlap)

## 5. Country breakdown (top markets, pooled within pair)
NOTE: the sample was not stratified by country, this rate is in-sample and cannot be generalized to the population. No CI computed, only raw rate and n shown.

- **chatbot / us**: any-friction raw rate %20.6 (n=34)
- **chatbot / br**: any-friction raw rate %45.2 (n=42)
- **chatbot / de**: any-friction raw rate %38.3 (n=60)
- **chatbot / fr**: any-friction raw rate %24.5 (n=53)
- **face / us**: any-friction raw rate %38.5 (n=135)
- **face / br**: any-friction raw rate %41.1 (n=56)
- **face / de**: any-friction raw rate %45.5 (n=22 ⚠)
- **face / fr**: any-friction raw rate %66.7 (n=18 ⚠)

