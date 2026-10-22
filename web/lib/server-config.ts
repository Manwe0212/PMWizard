type ServerConfig = {
  apiUrl: string;
  projectId: string;
  tenantId: string;
  userId: string;
  permissions: string;
};

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for PMWizard Web server routes.`);
  }
  return value;
}

export function getServerConfig(): ServerConfig {
  return {
    apiUrl: required("PMWIZARD_API_URL").replace(/\/$/, ""),
    projectId: required("PMWIZARD_PROJECT_ID"),
    tenantId: required("PMWIZARD_TENANT_ID"),
    userId: required("PMWIZARD_USER_ID"),
    permissions: required("PMWIZARD_PERMISSIONS"),
  };
}

export function backendHeaders(config: ServerConfig): HeadersInit {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-PMWizard-Tenant-ID": config.tenantId,
    "X-PMWizard-User-ID": config.userId,
    "X-PMWizard-Permissions": config.permissions,
  };
}
