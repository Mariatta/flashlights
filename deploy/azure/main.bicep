// Flashlights on Azure: Postgres Flexible Server, Azure
// Cache for Redis, and Container Apps for the minimum formation, web plus
// one worker, with the release command as a job. The image is pulled from
// a registry by tag; object storage is an S3-compatible bucket from another
// provider (Azure Blob does not speak the S3 API), given as
// parameters. Deploy into an existing resource group:
//
//   az deployment group create -g <group> -f main.bicep -p @params.json
//
targetScope = 'resourceGroup'

@description('A short name for this instance; resource names derive from it.')
@minLength(3)
@maxLength(20)
param name string

@description('Azure region.')
param location string = resourceGroup().location

@description('The container image, by tag, such as ghcr.io/mariatta/flashlights:1.0.0 (slim) or :1.0.0-full.')
param image string

@description('The hostnames the portal answers on, comma-separated.')
param allowedHosts string

@secure()
param secretKey string

@secure()
param fernetKey string

@description('smtp://user:password@host:port/?tls=true, from any provider.')
@secure()
param emailUrl string

@description('The address the portal\'s email comes from.')
param defaultFromEmail string

@description('Object storage (S3 API) from any provider: the endpoint URL.')
param s3EndpointUrl string
param s3Bucket string
@secure()
param s3AccessKeyId string
@secure()
param s3SecretAccessKey string

@description('Postgres administrator password.')
@secure()
param postgresPassword string

@description('Instance identity and switches (portal/branding.py, the lite profile).')
param siteTitle string = 'Flashlights'
param brandPreset string = 'beam'
param volunteeringEnabled string = 'true'
param sponsorshipEnabled string = 'true'
param statsPublic string = 'true'

var postgresUser = 'flashlights'
var postgresDb = 'flashlights'

resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${name}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${name}-db'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: postgresUser
    administratorLoginPassword: postgresPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: postgresDb
}

resource postgresAzureAccess 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'allow-azure-services'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: '${name}-redis'
  location: location
  properties: {
    sku: { name: 'Basic', family: 'C', capacity: 0 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// The password and the key are URL components: any character is allowed in
// them, so they are encoded, or a '@' or '/' would be read as the host.
var databaseUrl = 'postgresql://${postgresUser}:${uriComponent(postgresPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/${postgresDb}?sslmode=require'
var redisUrl = 'rediss://:${uriComponent(redis.listKeys().primaryKey)}@${redis.properties.hostName}:${redis.properties.sslPort}/0'

// Every process gets the same environment: the boot contract (portal/boot.py).
var secrets = [
  { name: 'secret-key', value: secretKey }
  { name: 'fernet-key', value: fernetKey }
  { name: 'database-url', value: databaseUrl }
  { name: 'redis-url', value: redisUrl }
  { name: 'email-url', value: emailUrl }
  { name: 's3-access-key-id', value: s3AccessKeyId }
  { name: 's3-secret-access-key', value: s3SecretAccessKey }
]
var env = [
  { name: 'SECRET_KEY', secretRef: 'secret-key' }
  { name: 'FERNET_KEY', secretRef: 'fernet-key' }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'REDIS_URL', secretRef: 'redis-url' }
  { name: 'EMAIL_URL', secretRef: 'email-url' }
  { name: 'AWS_ACCESS_KEY_ID', secretRef: 's3-access-key-id' }
  { name: 'AWS_SECRET_ACCESS_KEY', secretRef: 's3-secret-access-key' }
  { name: 'DJANGO_ALLOWED_HOSTS', value: allowedHosts }
  { name: 'DJANGO_DEFAULT_FROM_EMAIL', value: defaultFromEmail }
  { name: 'USE_OBJECT_STORAGE', value: 'true' }
  { name: 'AWS_STORAGE_BUCKET_NAME', value: s3Bucket }
  { name: 'AWS_S3_ENDPOINT_URL', value: s3EndpointUrl }
  { name: 'SITE_TITLE', value: siteTitle }
  { name: 'BRAND_PRESET', value: brandPreset }
  { name: 'VOLUNTEERING_ENABLED', value: volunteeringEnabled }
  { name: 'SPONSORSHIP_ENABLED', value: sponsorshipEnabled }
  { name: 'STATS_PUBLIC', value: statsPublic }
  { name: 'PORT', value: '8000' }
]

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${name}-web'
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'web'
          image: image
          command: [ 'gunicorn', '-c', 'config/gunicorn.conf.py', 'portal.wsgi:application', '--log-file', '-' ]
          env: env
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${name}-worker'
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: { secrets: secrets }
    template: {
      containers: [
        {
          name: 'worker'
          image: image
          command: [ 'sh', 'bin/worker' ]
          env: env
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

// The release step: migrations, run by hand after each image change:
//   az containerapp job start -g <group> -n <name>-release
resource release 'Microsoft.App/jobs@2024-03-01' = {
  name: '${name}-release'
  location: location
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'release'
          image: image
          command: [ 'sh', '-c', 'python manage.py createcachetable && python manage.py migrate' ]
          env: env
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
    }
  }
}

output webUrl string = 'https://${web.properties.configuration.ingress.fqdn}'
