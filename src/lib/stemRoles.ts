// stemRoles.ts - work out a stem's role from the name the USER gave the file (whole words, not substrings).
export type InferredRole = "beat" | "lead" | "adlib" | "backing" | "feature" | "response" | "intro" | "outro" | "unassigned";
export interface RoleGuess { role: InferredRole; confidence: "name" | "guess" | "none"; reason: string }

const has = (t: Set<string>, ...w: string[]) => w.some((x) => t.has(x));

export function tokens(name: string): string[] {
  return (name || "")
    .replace(/\.[a-z0-9]{2,5}$/i, "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

export function inferRole(name: string): RoleGuess {
  const tk = tokens(name);
  const t = new Set(tk);
  const joined = " " + tk.join(" ") + " ";
  const phrase = (p: string) => joined.includes(" " + p + " ");
  const leadWord = has(t, "lead", "main", "vocal", "vocals", "vox", "acapella", "acappella", "acap");

  if (phrase("backing track") || phrase("minus one") || phrase("type beat") || phrase("two track") ||
      has(t, "beat", "beats", "instrumental", "instru", "inst", "instrument", "riddim", "karaoke", "2track", "playback"))
    return { role: "beat", confidence: "name", reason: "name says beat/instrumental" };

  if (phrase("ad lib") || phrase("ad libs") || has(t, "adlib", "adlibs"))
    return { role: "adlib", confidence: "name", reason: "name says ad-lib" };
  if (has(t, "harmony", "harmonies", "harm", "stack", "stacks", "stacked", "stacking"))
    return { role: "adlib", confidence: leadWord ? "guess" : "name", reason: "name says harmony/stack" };

  if (phrase("back vocal") || phrase("back vocals") || phrase("back up") || phrase("back vox") ||
      has(t, "backing", "backup", "backups", "bv", "bvs", "bgv", "bgvs", "bvox", "bg", "double", "doubles", "doubled",
          "dub", "dubs", "dbl", "group", "choir", "gang", "crowd", "layer", "layers"))
    return { role: "backing", confidence: leadWord ? "guess" : "name", reason: "name says backing/double/group" };

  if (has(t, "feature", "feat", "ft", "guest")) return { role: "feature", confidence: "name", reason: "name says feature" };
  if (has(t, "intro")) return { role: "intro", confidence: "name", reason: "name says intro" };
  if (has(t, "outro")) return { role: "outro", confidence: "name", reason: "name says outro" };
  if (has(t, "response", "resp", "reply")) return { role: "response", confidence: "name", reason: "name says response" };

  if (leadWord || has(t, "dry", "voice", "rap", "sing", "singing")) {
    if (tk.some((x) => /^[2-9]$/.test(x)) && !has(t, "lead", "main"))
      return { role: "lead", confidence: "guess", reason: "numbered vocal: second take or backing? check it" };
    return { role: "lead", confidence: "name", reason: "name says lead/vocal" };
  }
  if (has(t, "verse", "hook", "chorus", "bridge", "prechorus", "pre", "refrain"))
    return { role: "lead", confidence: "guess", reason: "section name usually means the lead" };
  return { role: "unassigned", confidence: "none", reason: "name does not say what this is" };
}
