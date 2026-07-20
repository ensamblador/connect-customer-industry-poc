# cdk_constructs.webhosting — shared static website hosting construct

Industry-agnostic CDK **construct** that deploys a Vite-built website to a
private S3 bucket served through CloudFront with Origin Access Control (OAC),
plus an optional demo data-viewer (`/datos*`) that renders DynamoDB tables as
HTML. Each per-industry app instantiates it from its `website_stack.py`,
passing its own values in — this module imports **no** ambient `config`.

## What it creates

- A private S3 bucket (`BLOCK_ALL` public access).
- A CloudFront distribution with `S3BucketOrigin.with_origin_access_control`
  (OAC), `REDIRECT_TO_HTTPS`, and SPA-style 403/404 → `/index.html` mapping.
- A `BucketDeployment` that uploads the built site and invalidates the
  distribution cache on deploy.
- (Optional) a data-viewer Lambda + regional REST API behind the `/datos*`
  CloudFront behavior, granted `dynamodb:Scan` on the given tables only.

## Parameters (props)

| Prop | Purpose |
|---|---|
| `assets_path` | Absolute path to the built site (`website/dist`). Validated at synth. |
| `data_viewer_asset_path` | Absolute path to the industry's data-viewer Lambda dir. `None` disables `/datos*`. |
| `data_viewer_tables` | `{ENV_VAR: table_name}` handed to the Lambda; drives the `Scan` grant. |
| `price_class`, `http_version`, `viewer_protocol_policy`, `default_root_object`, `invalidation_paths`, `destination_key_prefix` | CloudFront + BucketDeployment knobs. |
| `data_viewer_description` | Description on the data-viewer Lambda + REST API. |

## What stays per industry

- The built site (`website/**`) and its `website/dist` output.
- The data-viewer Lambda source (`lambdas/code/data_viewer/`) — it carries the
  industry branding + table titles.
- The `WEBSITE_*` and table-name values in the app's `config.py`.

Build the site first, then deploy:

```bash
cd website && npm run build && cd ..
cdk deploy CX-<INDUSTRY>-WEBSITE
```

Set `BUILD_WEBSITE = False` in the app's `config.py` to synthesize an empty
stack (e.g. when `website/dist` has not been built yet).
