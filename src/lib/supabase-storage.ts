import {
  DeleteObjectCommand,
  GetObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { env } from "./env";

const storageClient = new S3Client({
  region: env.SUPABASE_STORAGE_REGION,
  endpoint: env.SUPABASE_STORAGE_S3_ENDPOINT,
  forcePathStyle: true,
  credentials: {
    accessKeyId: env.SUPABASE_STORAGE_ACCESS_KEY_ID,
    secretAccessKey: env.SUPABASE_STORAGE_SECRET_ACCESS_KEY,
  },
});

type UploadAudioOptions = {
  buffer: Buffer;
  key: string;
  contentType?: string;
};

export async function uploadAudio({
  buffer,
  key,
  contentType = "audio/wav",
}: UploadAudioOptions): Promise<void> {
  await storageClient.send(
    new PutObjectCommand({
      Bucket: env.SUPABASE_STORAGE_BUCKET,
      Key: key,
      Body: buffer,
      ContentType: contentType,
    }),
  );
}

export async function deleteAudio(key: string): Promise<void> {
  await storageClient.send(
    new DeleteObjectCommand({
      Bucket: env.SUPABASE_STORAGE_BUCKET,
      Key: key,
    }),
  );
}

export async function getSignedAudioUrl(key: string): Promise<string> {
  const command = new GetObjectCommand({
    Bucket: env.SUPABASE_STORAGE_BUCKET,
    Key: key,
  });
  return getSignedUrl(storageClient, command, { expiresIn: 3600 });
}
