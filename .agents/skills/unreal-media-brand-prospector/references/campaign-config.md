# UMG campaign configuration

Validate against installed sibling `../unreal-prospecting-core/schemas/campaign-config.schema.json` or repository path `shared/prospecting-core/schemas/campaign-config.schema.json`. `discovery_scope: open` with `verticals: []` is valid. Supported controls include geography, required/preferred signals, include/exclude lists, re-engagement, cooldown, evidence age, target/deep limits, minimum score, output formats, and local history path.

UMG campaigns may add:

```json
"opportunity_filter": {
  "include_any": ["product_photography", "product_video"],
  "exclude": ["ugc_ad"]
}
```

The controlled vocabulary is exactly `product_photography`, `product_video`, and `ugc_ad`. Search intent is not prospect evidence. A qualified result must provide evidence-linked `opportunity_matches` for at least one included kind and none of the excluded kinds.

Examples live at installed sibling `../unreal-prospecting-core/examples/campaigns/` or repository path `fixtures/prospecting/campaigns/`, including the ready-to-use `umg-product-visuals-no-ugc.json` campaign.
