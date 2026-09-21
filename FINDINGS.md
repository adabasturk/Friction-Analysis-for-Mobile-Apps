# Mobile Apps: Funnel Friction Analysis — Findings

An analysis of conversion friction in AI mobile apps, built from App Store reviews.
Two Turkish app studios (Codeway, HubX) are compared as matched pairs within the
same verticals.

**Data:** 9,432 reviews across 8 countries (us, gb, de, tr, br, in, fr, jp) and
4 apps. 6,961 carry substantive content. 998 were converted into structured data
by a local LLM.

| Vertical | Codeway | HubX | Reviews |
|---|---|---|---|
| AI chatbot | Chat AI: Ask Agent Anything | AI Chatbot - Nova | 3,368 / 3,565 |
| Face / portrait editing | Retake AI Face & Selfie Editor | ReShoot: AI Face Photo Editor | 1,772 / 727 |

Why matched pairs: comparing arbitrary popular apps cannot separate a studio's
monetization choices from category norms. Holding the vertical fixed makes the
remaining difference attributable to the studio.

Rates below come from a stratified random sample of 150 reviews per app, weighted
back to each app's real rating distribution. Where a difference is not
statistically significant it is marked as directional — still worth reading, not
worth betting on.

---

## 1. The studio difference is not uniform — it lives in the face-editing vertical

The face-editing pair produced three significant differences. The chatbot pair
produced none: across all nine friction categories, the confidence intervals
overlap.

| | Retake (Codeway) | ReShoot (HubX) | |
|---|---|---|---|
| Reviews with no friction | 48.2% | 67.1% | significant |
| Paywall timing complaints | 14.1% | 6.3% | significant |
| Price level complaints | 9.0% | 1.6% | significant |
| Free quota complaints | 9.0% | 5.3% | directional |
| Paid but still limited | 13.2% | 10.7% | directional |

Half of Retake's reviews register some friction, against a third of ReShoot's. On
price, the gap is 5.6×.

Codeway's chatbot, meanwhile, is indistinguishable from HubX's. Whatever drives
the gap is not a house style — it is a set of decisions made inside one vertical.

The raw ratings point the same way. Retake's 1-star share is 30.7% of all its
reviews; ReShoot and Nova sit at 19.5%, Chat AI at 11.6%.

---

## 2. Paywall timing provokes a harsher reaction than price

Cross-tabulating friction type against star rating:

| Friction type | 1-star share | 5-star share | n |
|---|---|---|---|
| paywall_timing | 77.8% | 4.4% | 45 |
| subscription_trap | 67.6% | 17.6% | 34 |
| referral_gate | 60.0% | 20.0% | 5 |
| onboarding_confusion | 48.9% | 26.7% | 45 |
| free_quota_limit | 41.7% | 13.9% | 36 |
| price_level | 36.0% | 32.0% | 25 |
| quality_gap | 24.0% | 36.0% | 25 |

A third of the users who call the app expensive still leave five stars. That is a
grumble. Three quarters of the users who complain about *when* the paywall
appeared leave one star. That is an exit.

Before touching price, move the paywall. It is the higher-leverage intervention.

The effect concentrates in Retake: among its 1-star reviews, 30.2% concern paywall
timing (n=63), against 14.1% across the app as a whole.

---

## 3. Face editors stop users before they have seen the product

Where the friction occurs:

| | before_first_use |
|---|---|
| Retake AI (face) | 29.1% |
| ReShoot (face) | 19.2% |
| Nova (chatbot) | 11.6% |
| Chat AI (chatbot) | 9.6% |

In face editors, users hit friction without having tried the product — roughly
three times as often as in chatbots. Within each pair the difference is not
significant; between verticals it is large and consistent.

The product mechanics explain it. A chatbot's first message is free, so the user
sees value before any ask. In a face editor the user uploads a photo, invests
effort, and meets the paywall before seeing a result.

The clustering points the same way. Cluster 5 (n=630, mean rating 1.60) is the
free-trial-and-cancellation cluster. Normalized by each app's review volume, face
editors land in it at roughly twice the rate:

| | Share of reviews in cluster 5 |
|---|---|
| Retake AI | 11.6% |
| ReShoot | 11.0% |
| Nova | 5.2% |
| Chat AI | 4.7% |

Here the two face editors behave alike. The gap in section 1 is about how hard
each one pushes; this is about what the category does to everyone in it.

---

## 4. The most valuable segment is larger in face editors

`would_pay_signal = conditional` marks users who were close to paying and stopped
for a stated reason — the segment worth designing for.

| | conditional |
|---|---|
| Retake AI | 12.3% |
| ReShoot | 11.9% |
| Chat AI | 9.2% |
| Nova | 6.0% |

None of these differences is significant on its own, but the ordering matches
everything else: the face pair sits above the chatbot pair, and Nova is lowest.

Two mechanics surfaced from the clusters and were added to the schema afterwards.
`paid_but_still_limited` — buying a lifetime tier and remaining capped — runs at
13.2% and 10.7% in the face pair against about 6% in the chatbot pair.
`referral_gate` — invite three friends for unlimited access — appears in only 13
records overall, too few to rate, but it exists in the wild and it produces 1-star
reviews 60% of the time.

---

## 5. Directional differences inside the chatbot pair

Nothing here clears the significance bar, and with 150 records per app it would
need a gap of roughly 12 points to do so. Two differences are wide enough to be
worth a look:

- **subscription_trap:** Nova 7.4%, Chat AI 3.3%. More than double, in the
  category that produces 1-star reviews two thirds of the time.
- **performance:** Nova 4.2%, Chat AI 0.7%. A six-fold gap on a category that is
  an engineering problem rather than a monetization one.

---

## 6. Country patterns

The sample was stratified by app and rating, not by country, so these are raw
rates within the sample rather than estimates for each market. They are reported
because the spread is too wide to ignore.

| | any-friction rate | n |
|---|---|---|
| Chatbot, Brazil | 45.2% | 42 |
| Chatbot, Germany | 29.8% | 60 |
| Chatbot, France | 24.8% | 53 |
| Chatbot, US | 20.6% | 34 |
| Face, France | 66.7% | 18 |
| Face, Germany | 45.5% | 22 |
| Face, Brazil | 41.1% | 56 |
| Face, US | 38.5% | 135 |

Brazil's chatbot rate is more than double the US rate. The French and German face
cells rest on fewer than 25 records each and should be treated as a prompt to
collect more, not as a finding.

---

## 7. Method notes

**The clusters organized by language, not by topic.** KMeans at k=12 (the best of
k ∈ {8, 12, 16, 20} by silhouette, 0.089) produced a Turkish cluster, a German one,
a Japanese one, a Portuguese one, a French one. `nomic-embed-text` encodes language
first and topic second on a multilingual corpus.

That broke retrieval: a Turkish question returned 100% Turkish reviews regardless
of topic. The fix has two layers — detect a country in the question and restrict
the pool before computing similarity, then translate the query into that market's
language before embedding. Top-1 similarity for the Brazil query rose from 0.51 to
0.73, and for the Japan query from 0.63 to 0.79.

**Labelling a cluster is not the same as reading it.** The five reviews closest to
cluster 6's centroid were keyboard mash (`Ggshsjsjsjjdjddndjjd`), so the cluster
was labelled "669 junk records." A random sample of twenty from the same cluster
contained `3 messages? Are you kidding!` — a direct quota complaint — along with
several concrete product reports. A record-level filter flagged 9 junk records out
of 6,961. Dropping the cluster wholesale would have deleted some of the clearest
paywall signal in the dataset.

**Sampling was split into two frames.** The estimation frame (600 records) is a
stratified random sample, 150 per app by rating band, and every percentage here
comes from it, weighted by the inverse of each record's selection probability. The
discovery frame (420 records) was drawn purposively from complaint clusters and
contributes quotes and hypotheses only. An assertion inside the rate function
enforces the separation in code rather than by convention.

---

## 8. The model was chosen by measurement, and its ceiling was measured too

Four candidates, scored against 8 hand-labelled reviews in three languages:

| Model | friction_type | would_pay_signal | sec/record |
|---|---|---|---|
| **gemma3:4b** | **7/8** | **8/8** | 15.7 |
| qwen2.5:3b | 6/8 | 6/8 | 6.9 |
| granite3.3:2b | 4/8 | 7/8 | 7.1 |
| llama3.2:3b | 3/8 | 6/8 | 7.4 |

The failure modes taught more than the totals. llama3.2:3b answered `price_level`
to six of eight cases — collapsed to the majority class, which its middling
aggregate score concealed. granite3.3:2b invented an enum value that does not exist
in the schema (`payment_confusion`).

**The same model behaved very differently across two tasks.** Extracting 998
records, gemma3:4b returned 1.3% invalid output. Asked to generate hypotheses from
the resulting observations, it produced 24 items, none usable: it read
`trigger_moment` as "how often the app was triggered" and proposed *increasing*
friction, mistook a confidence-interval bound for a user segment, and treated a
data-cleaning step as a product feature.

Classification asks for reading comprehension. Hypothesis generation asks the model
to hold several fields in relation to one another. A 4B model clears the first bar
and not the second. Both outputs are kept in this repository for comparison.

**The validation layer grew the same way three times.** Generating SQL, the model
in turn dropped the `COUNT(*) AS n` column, omitted a rating filter the question had
asked for, and added a country filter the question never mentioned. The last is the
most dangerous: the query still returns a plausible number, silently scoped to the
wrong population.

Telling the model what it got wrong and asking again changed nothing — at
`temperature=0` it returned byte-identical SQL. All three were fixed in code:
inject the missing column, strip the ungranted filter, refuse the query when
neither is possible.

The same pattern appeared during extraction. With concrete values like `9.99/week`
in the prompt's example JSON, the model copied them into short reviews — a
three-word, five-star French review came back tagged `subscription_trap` at
`9.99/week`. Replacing the example values with placeholders ended it.

Working with small local models, the reliable move is not to ask again but to
repair the output mechanically.

---

## 9. Limitations

**No control apps.** Only AI apps were studied, so this cannot address whether the
monetization playbook predates the AI wave.

**150 records per app.** At a rate near 30% the standard error is about 3.7 points.
Differences under roughly 12 points are marked directional rather than reported as
findings.

**Country rates are within-sample.** The design stratifies by app × rating band,
not by country; 600 records across 4 apps and 8 countries leaves about 19 per cell.

**No language column.** Country is used as a proxy. A user writing in German may be
in Austria.

**The App Store RSS feed caps at roughly 500 reviews per app-country.** The sample
skews recent.

**Significance was assessed by interval overlap** — conservative, so it will miss
some real differences and will not manufacture one.

**Product flows were not inspected directly.** Findings come from review text; no
paywall was observed first-hand, so how each app actually sequences its paywall is
the next thing to verify.

---

## Data and code

The whole pipeline runs locally: collection, embeddings (`nomic-embed-text`),
extraction (`gemma3:4b`), SQLite, analysis. No external API calls. Hardware: a 2020
MacBook Pro, Intel i5, 8 GB RAM, no GPU. Extraction took 6 hours 41 minutes across
two overnight runs.
