// lib/constants.js

export const API_VERSION         = process.env.NEXT_PUBLIC_API_VERSION

export const SERVICE_URL_CONFIGS = process.env.NEXT_PUBLIC_SERVICE_URL_CONFIGS
export const SERVICE_URL_AGENTS  = process.env.NEXT_PUBLIC_SERVICE_URL_AGENTS

export const CONFIGS_PREFIX      = `/api/${API_VERSION}/configs`
export const AGENTS_PREFIX       = `/api/${API_VERSION}/agents`
export const MESSAGES_PREFIX     = `/api/${API_VERSION}/messages`
export const TURNS_PREFIX        = `/api/${API_VERSION}/turns`
export const TEMPLATES_PREFIX    = `/api/${API_VERSION}/templates`
