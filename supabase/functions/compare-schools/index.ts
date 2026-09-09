import { createHandler } from './handler.mjs';

Deno.serve(createHandler({
  getEnv: (name: string) => Deno.env.get(name),
}));
