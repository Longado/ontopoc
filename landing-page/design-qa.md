# OntoPoc Demo Design QA

## Evidence

- Source visual truth: local screenshot, 2026-08-29 (not committed)
- Implementation: local temporary screenshot (not committed)
- Side-by-side comparison: local temporary screenshot (not committed)
- Source pixels: `2522 × 1114`
- Implementation pixels and CSS viewport: `1440 × 900` at device scale factor `1`
- Comparison normalization: both full views were scaled to a common comparison height without changing aspect ratio; browser chrome was excluded from the implementation capture.
- State: Trial modal open, `OntologySpec` stage selected, `Graph` view selected, relationship evidence shown in the inspector.

## Full-view comparison

The implementation preserves the reference's operational hierarchy: black status shell, warm-paper graph field, cobalt active state, directed graph in the main region, and a persistent evidence inspector on the right. It intentionally shows an ontology type graph instead of the reference's instance-level impact trace, because the committed artifact contains entity types, relation types, and a candidate rule but no customer instances or execution result.

The document-modeling launch view is a product extension grounded in the same visual system rather than a direct recreation of the reference. It was checked separately at `1440 × 900` and `390 × 900` for layout and interaction behavior.

## Focused comparison

Focused inspection covered node typography, selected-state contrast, the two parallel supplier-to-material relationships, relationship labels, the candidate-rule node, the 300 px inspector, and the bottom query trigger. These details were readable in the original implementation capture, so separate cropped images were not needed.

## Required fidelity surfaces

- Fonts and typography: the implementation uses the existing product display and monospace hierarchy; graph metadata, node labels, and inspector evidence remain legible at the target desktop viewport.
- Spacing and layout rhythm: the stage rail, graph canvas, and inspector retain stable proportions with no desktop horizontal overflow or clipped persistent controls.
- Colors and visual tokens: ink, warm paper, cobalt, thin rules, and selected states match the supplied visual direction and the existing product tokens.
- Image and asset fidelity: the interface uses the supplied brand asset and the existing icon library. No visible source asset was replaced with CSS art, placeholder imagery, or handcrafted SVG.
- Copy and content: labels accurately describe a read-only `synthetic_demo`; preview, compilation, validation, live-model, and writeback boundaries are explicit.

## Interaction and browser checks

- `Graph / Details`, node and edge selection, fit/reset, deterministic query, refusal response, Esc close, and focus return were exercised.
- The document-modeling scenario selector, exact-text Generate action, preview-only route, unsupported edited input, and compiled supply-chain route were exercised.
- Desktop and 390 px captures had no horizontal overflow.
- Browser console: `0` errors and `0` warnings on a fresh desktop graph page; `0` errors for the document-modeling checks.

## Comparison history

1. First graph capture: P2 node copy overlapped connection handles and made the material/rule labels hard to read.
2. Fix: node copy received an explicit layout region; desktop and 390 px captures were repeated.
3. Final graph capture: node copy, parallel relationships, candidate rule, and inspector are readable. No actionable P0, P1, or P2 visual findings remain.

## Follow-up polish

- P3: a future iteration may add a dedicated source visual for the document-modeling launch view. This does not block the current demo because its layout follows the verified product shell and all core controls are usable.

final result: passed
