type ServerConfig = {
  apiUrl: string;
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
  };
}
