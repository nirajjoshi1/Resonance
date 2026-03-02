import { z } from "zod";
import { TRPCError } from "@trpc/server";
import { prisma } from "@/lib/db";
import { deleteAudio } from "@/lib/r2";
import { createTRPCRouter, orgProcedure } from "../init";

export const voicesRouter = createTRPCRouter({
  getAll: orgProcedure
    .input(
      z
        .object({
          query: z.string().trim().optional(),
        })
        .optional(),
    )
    .query(async ({ ctx, input }) => {
      const searchFilter = input?.query
        ? {
          OR: [
            { 
              name: { 
                contains: input.query, mode: "insensitive" as const
              } 
            },
            {
              description: {
                contains: input.query,
                mode: "insensitive" as const,
              },
            },
          ],
        }
        : {};

      const [custom, system] = await Promise.all([
        prisma.voice.findMany({
          where: {
            variant: "CUSTOM",
            orgId: ctx.orgId,
            ...searchFilter,
          },
          orderBy: { createdAt: "desc" },
          select: {
            id: true,
            name: true,
            description: true,
            category: true,
            language: true,
            variant: true,
          },
        }),
        prisma.voice.findMany({
          where: {
            variant: "SYSTEM",
            ...searchFilter,
          },
          orderBy: { name: "asc" },
          select: {
            id: true,
            name: true,
            description: true,
            category: true,
            language: true,
            variant: true,
          },
        }),
      ]);

      return { custom, system };
    }),

    delete: orgProcedure
      .input(z.object({ id: z.string() }))
      .mutation(async ({ ctx, input }) => {
        const voice = await prisma.voice.findUnique({
          where: {
            id: input.id,
            variant: "CUSTOM",
            orgId: ctx.orgId,
          },
          select: { id: true, r2ObjectKey: true },
        });

        if (!voice) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Voice not found",
          });
        }

        await prisma.voice.delete({ where: { id: voice.id } });

        if (voice.r2ObjectKey) {
          // In production, consider background jobs, retires, cron jobs etc.
          await deleteAudio(voice.r2ObjectKey).catch(() => {});
        }

        return { success: true };
      }),
});
