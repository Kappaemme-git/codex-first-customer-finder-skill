# Identity normalization

The canonical key is a conservative registrable-domain approximation plus normalized company names, aliases, public social handles, and explicit parent/subbrand/agency relationships.

`normalize_domain.py` removes schemes, credentials, ports, paths, query strings, fragments, `www`, and common storefront subdomains. The Python standard library has no public suffix list. The utility handles a small documented set of common multi-part suffixes and otherwise uses the final two labels. Unfamiliar country suffixes, shared hosting, marketplaces, franchises, and ambiguous parent/subbrand structures require human review rather than a confident merge.

Company-name comparison lowercases, transliterates for comparison, removes punctuation, and strips common terminal legal suffixes. It does not prove legal identity.
