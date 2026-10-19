# Flashlights on Azure

`main.bicep` provisions one instance: Postgres Flexible Server, Azure Cache
for Redis, a Container Apps environment with the `web` and `worker`
processes of the minimum formation, and a manual job for the release step
(migrations). Object storage is an S3-compatible bucket from another
provider, Cloudflare R2 or Backblaze B2 for instance, because Azure Blob
does not speak the S3 API; its four values are parameters.

1. Push an image to a registry the environment can pull from, or use a
   public tag.
2. Copy `params.example.json` to `params.json` and fill it in. Generate
   `secretKey` and `fernetKey`; the Fernet command is in the deployment
   guide. The Postgres password may contain any character; the template
   encodes it into `DATABASE_URL`.
3. `az group create -n <group> -l <region>`
4. `az deployment group create -g <group> -f main.bicep -p @params.json`
5. `az containerapp job start -g <group> -n <name>-release`, then after
   every image change.
6. Set the site domain (deployment guide, One-time configuration) and add
   the custom domain to the web app's ingress.

`params.json` holds secrets: keep it out of git (it is ignored).
