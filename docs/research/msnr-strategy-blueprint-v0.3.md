# PIPSLAYER — MALAYSIAN MSNR STRATEGY BLUEPRINT

Version 0.3 — Historical Market Memory integrated.

Status: Accepted working blueprint; research and definition work ongoing.

> **Provenance note.** This file preserves the owner-approved v0.3 specification as supplied in the Pipslayer project handover. Section numbers (3.1–3.19) follow the handover document in which the blueprint was supplied, so existing references such as "§3.4" remain valid. The wording below is the approved text; it has not been shortened or reinterpreted. Appendix A reproduces the handover's list of outstanding specification work and is not part of the approved blueprint text itself.

---

## 3.1 Strategy identity

MSNR identifies meaningful market structures and support/resistance levels, examines their relationships across timeframes, observes price behaviour when those areas are revisited, and evaluates whether lower-timeframe reactions provide trading opportunities.

The strategy must preserve the owner's understanding while allowing competing mechanical interpretations to be researched.

## 3.2 Timeframe framework

Primary: H4 → H2 → M15.

- H4: Broad market storyline and structural A/V levels.
- H2: Setup structures, V-levels, GAPs and relationships to H4.
- M15: Price reactions, confirmation candidates and entry evaluation.

Alternative configurations:

- PRIMARY_M5: H4 → H2 → M5. Inactive alternative.
- TWO_H_ONE_H: H2 setup → H1 reaction, without automatically assuming an H4 reference.

The primary configuration remains H4 → H2 → M15.

## 3.3 Equilibrium

Equilibrium is an owner-defined MSNR concept, not simply the 50% midpoint of a range.

It concerns different MSNR structures on different timeframes occupying the same relevant price area.

Example:

- H4 V-level.
- H2 GAP.
- M15 GAP breakout.

Different structure types can reinforce the significance of the same area.

Equilibrium is not mandatory for every setup.

Unresolved research:

- Price-distance tolerance.
- Qualifying timeframe relationships.
- Overlap versus proximity.
- Multiple structures.
- How relationships evolve during interaction.

## 3.4 A/V structural levels

A-level: Peak in the closing-price line, representing potential resistance.

V-level: Valley in the closing-price line, representing potential support.

The structural anchor is closing-price/body-price behaviour, not automatically the wick high or low.

Three candidate recognition methods must be preserved for comparison:

1. Closing-price line turning points — primary visual reference.
2. Candle-direction transitions — bullish-to-bearish for A, bearish-to-bullish for V.
3. Configurable pivot-depth detection using neighbouring candles.

No fixed candle count has been approved.

Separate these timestamps:

- formed_at: candidate turning candle closes.
- recognised_at: structure becomes objectively identifiable using available closed-candle information.
- confirmed_at: subsequent behaviour satisfies an applicable confirmation interpretation.

Never use future candles to pretend a structure was recognisable earlier.

## 3.5 A/V structural hierarchy

Preserve four structural scales:

- Master swing.
- Secondary swing.
- Local swing.
- Nested swing.

These labels describe structural scale, not A/V identity.

An A remains an A regardless of scale. A V remains a V regardless of scale.

Preserve individual structure identity, timeframe, scale, formation time, recognition time, enclosing relationships and higher/lower timeframe relationships.

Do not automatically assume a master swing is always stronger than a local swing.

## 3.6 Historical Market Memory

Historical A/V structures may remain relevant after price has moved away from them.

Do not restrict historical structures to a recent 12–24-hour window.

The system must be capable of identifying historical A/V levels ahead of current price, including structures formed days or weeks earlier.

Potential interactions include:

- Rejection.
- Consolidation.
- Shallow or deep penetration.
- Sweep and reclaim.
- Break and continuation.
- Break, return and role reversal.
- Multiple historical levels interacting during one movement.

Historical relevance is not permanent or guaranteed.

Preserve both:

- Current-window structures.
- Historical forward structures.

Research the effects of age, repeated interactions, previous rejections, structural scale and clustering.

Public research cited in the blueprint includes:

- Memory effects in stock price dynamics: evidences of technical trading (Scientific Reports, 2014).
- Chung and Bellotti, Evidence and Behaviour of Support and Resistance Levels in Financial Time Series.
- Carol Osler, Support for Resistance: Technical Analysis and Intraday Exchange Rates (2000).
- Osler's research on FX order clustering around round numbers.

These studies support research hypotheses, not guaranteed MSNR profitability.

## 3.7 A/V reaction zones

Keep the exact structural price distinct from its surrounding reaction zone.

Research alternatives:

- Fixed-distance zone.
- Candle-based zone.
- Volatility-based zone such as ATR.

No method is permanently selected.

Equal and nearly equal closing prices must also be researched to avoid duplicate structures while preserving contributing candle information.

## 3.8 GAP structures

Owner-defined GAP:

Two consecutive same-direction candles leaving a gap between the first candle's close and the second candle's open.

Bullish GAP:

- Two consecutive bullish candles.
- Second opens above first close.

Bearish GAP:

- Two consecutive bearish candles.
- Second opens below first close.

Preserve:

- level_price.
- gap_zone.

Research alternatives:

- Entire interval as zone.
- First candle close as primary level.
- Second candle open as momentum-start reference.

Research GAP reaction and GAP refinement/breakout-flip hypotheses.

Do not confuse this concept with ICT FVG.

## 3.9 Freshness and lifecycle

Freshness is distinct from structural validity, strength and historical significance.

Statuses:

- Fresh: no revisit.
- Unfresh: price interacted with the level.
- Renewed: qualifying breakthrough event under the selected interpretation.

Basic interpretation:

- Wick touch consumes freshness.
- Body close through may renew.
- Renewed can become unfresh after another interaction.
- Strong rejection does not restore freshness.
- Unfresh does not automatically mean invalid.

Record chronological interaction events:

- Wick touch.
- Body penetration.
- Close inside or beyond.
- Penetration depth.
- Rejection or continuation.
- Break and return.
- Renewal.
- Role reversal.
- Timeframe.
- Elapsed time.

Keep freshness simple. Interaction history is a research record, not a mandatory entry condition.

Historical Market Memory does not alter the three freshness statuses.

## 3.10 Confirmation candles

Owner-defined confirmation candle:

"A candle that touches the level just after its creation and closes in the direction of that level."

The precise meaning of "just after" is unresolved.

Six research candidates:

1. V-level CC.
2. A-level CC.
3. Bullish GAP CC.
4. Bearish GAP CC.
5. RBS CC.
6. SBR CC.

Confirmation is not the same as entry.

Public mechanical variations can be investigated but must not silently replace the owner's definition.

## 3.11 RBS and SBR

- RBS: Resistance Becomes Support.
- SBR: Support Becomes Resistance.

A close beyond a level is a break, not proof of successful role reversal.

Research:

- Initial break.
- Failed break.
- Return.
- Opposite-side retest.
- Successful or unsuccessful role reversal.
- Subsequent confirmation.

## 3.12 Nearby levels and confluence

Preserve three possible approaches:

1. Separate levels.
2. Merged zone.
3. Clustering that retains individual level identities.

Clustering is the preferred research representation, not a proven best trading method.

Record:

- Origin and timeframe.
- Creation and recognition times.
- Identity and scale.
- Lifecycle.
- Relationships.
- Interaction sequence.

Research shallow/deep rejection, repeated interaction, break-return, break-continuation, delayed reaction, sweep/reclaim and multiple-level interaction.

Investigate local versus deeper historical sweeps, secondary/master interactions, and corresponding A-level scenarios.

Do not automatically assume the lowest V or highest A is the strongest or final destination.

## 3.13 Market context

Research:

- Daily and weekly storyline.
- Higher-timeframe structure.
- Asian session highs/lows.
- London and New York behaviour.
- Previous highs/lows.
- Session boundaries.
- Historical A/V structures ahead.
- Psychological and round-number price references.

Keep psychological levels distinct from A/V structures.

Preserve both identities when they are near each other.

Broker time, UTC, daylight-saving changes and candle boundaries must be verified before session filters are treated as reliable.

## 3.14 LTF reaction and entry candidates

No single universal entry trigger has been approved.

Candidate families:

- Engulfing.
- Wick rejection.
- Close-back rejection.
- Strong displacement.
- Rejection candles.
- Holding or failing at a marked level.
- LTF structure shifts.
- Breakout and retest.
- Sweep and reclaim.
- Failed continuation.
- Consolidation breakout.
- Pullback continuation.
- Role-reversal retest.
- Continuation after a missed initial entry.

Candidates must be independently definable, testable, enabled/disabled, compared and combined.

No candidate is assumed profitable merely because it is registered.

## 3.15 Stops, targets and trade management

Stop candidates:

- Structural invalidation.
- Opposite side of reaction area.
- Level-based.
- Candle-based.
- Volatility-aware.
- Instrument-specific.

Targets:

- Next relevant MSNR level.
- Next fresh level.
- Session highs/lows.
- Other meaningful structures.

The owner's practical approach generally seeks approximately 2:1 or higher.

Research:

- Partial profit around 1:1.
- Breakeven.
- Trailing.
- Alternative management.
- No arbitrary maximum RR cap.

Medium Risk is the default research profile. Low, High and Adaptive may be added later. Adaptive setup-quality risk is outside initial scope.

## 3.16 Correlation and exposure

Eventually account for:

- Multiple simultaneous setups.
- Cross-instrument correlation.
- Total exposure.
- Risk by strategy and setup type.
- Position sizing independent of signal quality.

Initial instrument: XAUUSD.

Future symbols:
EURUSD, GBPUSD, NAS100, GBPJPY, USDJPY.

## 3.17 Historical validation

Requirements:

- No lookahead.
- Visual chart validation.
- Point-in-time formation and recognition.
- Chronological event processing.
- Tick simulation where possible.
- Realistic spread, costs and execution assumptions.
- Baseline comparisons.
- Rolling walk-forward.
- Untouched holdout.
- Robustness.
- Parameter-neighbourhood analysis.
- Effective independent episodes, not raw trade count alone.

Research master versus local, recent versus old, fresh versus interacted, one versus repeated rejection, recent-window versus older, local sweep versus deeper level, sweep/reclaim versus break/continue, isolated versus clustered, round-number confluence and timeframe/regime differences.

Measure reaction probability/distance, penetration depth, time to reaction, reclaim probability, continuation probability, repeated interaction and age effects.

Account for selection bias, overlapping observations, regimes and multiple levels participating in one movement.

Never use future information when reconstructing past knowledge.

A short dataset validates plumbing and detection mechanics, not profitability.

Preserve failed and inconclusive experiments.

## 3.18 Research brain and explainability

The future brain should explain:

- Why a setup qualified or was rejected.
- Which structures/timeframes contributed.
- Confirmation candidates.
- Freshness and interaction history.
- Structural hierarchy.
- Historical levels ahead.
- Round-number confluence.
- Risk and exposure.
- Candidate performance.
- Research gaps.
- Next experiment and rationale.

Preserve experiment history, failed hypotheses, evidence, lineage and reproducible configurations.

The brain must not automatically change validation rules or promote an unvalidated strategy to live trading.

Evolution begins with controlled comparisons and ablation, not unrestricted rule generation.

## 3.19 Execution boundary

Execution remains disabled until:

- Definitions are sufficiently formalised.
- Historical recognition is validated.
- Backtesting and simulation are trustworthy.
- Risk controls are verified.
- Robustness and holdout requirements pass.
- The owner explicitly approves progression.

A promising backtest is not permission for live trading.

---

## Appendix A — Outstanding specification work (from the project handover)

*This list was supplied in the handover alongside the blueprint. It is reproduced here for convenience and is not part of the approved v0.3 text.*

The following remain unresolved and must not be filled with arbitrary assumptions:

1. A/V recognition mechanics.
2. Equal/near-equal closes.
3. Recognition delay and confirmation timing.
4. GAP boundaries, size and eligibility.
5. H4/H2 Equilibrium relationships and tolerance.
6. CC timing.
7. Freshness renewal/retirement variants.
8. RBS/SBR confirmation.
9. LTF definitions and combination logic.
10. Zone widths.
11. Session/broker time.
12. Stops/targets.
13. Trade-management comparisons.
14. Data coverage/sample size.
15. Swing-scale classification.
16. Historical relevance/time decay.
17. Interaction/repeated-rejection metrics.
18. Local sweep/deeper-level research.
19. Psychological references and A/V confluence.

These are research and specification tasks, not permission to invent rules.
