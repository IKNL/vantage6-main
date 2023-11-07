/* eslint-disable @typescript-eslint/no-explicit-any */
import { EnvironmentConfig } from 'src/app/models/application/enivronmentConfig.model';

const env: EnvironmentConfig = {
  production: true,
  server_url: (window as any).env?.server_url || 'https://petronas.vantage6.ai',
  api_path: (window as any).env?.api_path || '',
  version: '0.0.0',
  algorithm_server_url: (window as any).env?.algorithm_server_url || '' //TODO: add default algorithm server url
};

export const environment = env;
