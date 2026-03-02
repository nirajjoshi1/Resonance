import { z } from "zod";
import { createEnv } from "@t3-oss/env-nextjs";

export const env = createEnv({
  server: {
    POLAR_ACCESS_TOKEN: z.string().min(1),
    POLAR_SERVER: z.enum(["sandbox", "production"]).default("sandbox"),
    POLAR_PRODUCT_ID: z.string().min(1),
    DATABASE_URL: z.string().min(1),
    APP_URL: z.string().min(1),
    SUPABASE_STORAGE_S3_ENDPOINT: z.string().url(),
    SUPABASE_STORAGE_REGION: z.string().min(1),
    SUPABASE_STORAGE_ACCESS_KEY_ID: z.string().min(1),
    SUPABASE_STORAGE_SECRET_ACCESS_KEY: z.string().min(1),
    SUPABASE_STORAGE_BUCKET: z.string().min(1),
    CHATTERBOX_API_URL: z.url(),
    CHATTERBOX_API_KEY: z.string().min(1),
  },
  experimental__runtimeEnv: {},
  skipValidation: !!process.env.SKIP_ENV_VALIDATION,
});
