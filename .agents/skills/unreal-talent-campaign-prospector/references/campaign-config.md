# Unreal Talent campaign configuration

Validate against installed sibling `../unreal-prospecting-core/schemas/campaign-config.schema.json` or repository path `shared/prospecting-core/schemas/campaign-config.schema.json`. Require buyer types and likely rights territory. Vertical and talent category remain optional. Open discovery uses `discovery_scope: open` and `verticals: []`.

Named talent remains disabled unless `approved_roster_path` is provided, authorization is explicit, and the campaign defines verticals, talent categories, and `campaign_channels`. Examples live at installed sibling `../unreal-prospecting-core/examples/campaigns/` or repository path `fixtures/prospecting/campaigns/`: open, sports brands, agencies, and re-engagement.
