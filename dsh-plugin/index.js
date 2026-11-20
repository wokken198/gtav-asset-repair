import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const name = "dsh-gta-tools";
export const inject = ["tools"];

const here = dirname(fileURLToPath(import.meta.url));
const vendorDir = join(here, "vendor");
const MAX_CHARS = 6000;

const pythonPath = () => process.env.GTA_TOOLS_PYTHON ?? "";
const texconvPath = () => process.env.GTA_TOOLS_TEXCONV ?? "";
const coreDir = () => process.env.GTA_TOOLS_CW ?? "";

const STORE_STUB = "was not found; run without arguments to install from the Microsoft Store";

function pythonCandidates() {
	const list = [];
	const configured = pythonPath();
	if (configured.length > 0) list.push([configured]);
	list.push(["python3"], ["python"]);
	if (process.env.LOCALAPPDATA) {
		list.push([
			join(process.env.LOCALAPPDATA, "Programs", "DeepSeek Harness", "resources", "runtime", "primary-runtime", "dependencies", "python", "python.exe"),
		]);
	}
	if (process.env.USERPROFILE) {
		list.push([join(process.env.USERPROFILE, ".dsh", "dsh-runtimes", "dsh-primary-runtime", "dependencies", "python", "python.exe")]);
	}
	return list;
}

const PROBE = "import sys, numpy, PIL; print(sys.executable)";

let resolved = null;

function spawnOnce(python, argv, timeoutMs) {
	const env = { ...process.env, PYTHONPATH: vendorDir, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" };
	return new Promise((resolve) => {
		execFile(
			python[0],
			[...python.slice(1), ...argv],
			{ cwd: here, env, timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024, windowsHide: true },
			(error, stdout, stderr) => resolve({ error, stdout: stdout ?? "", stderr: stderr ?? "" }),
		);
	});
}

async function resolvePython() {
	if (resolved !== null) return resolved;
	const missingDeps = [];
	for (const candidate of pythonCandidates()) {
		const probe = await spawnOnce(candidate, ["-c", PROBE], 30000);
		if (probe.error && probe.error.code === "ENOENT") continue;
		const blob = `${probe.stdout}\n${probe.stderr}`;
		if (blob.includes(STORE_STUB)) continue;
		if (probe.error === null || probe.error === undefined) {
			resolved = candidate;
			return candidate;
		}
		if (blob.includes("ModuleNotFoundError") || blob.includes("No module named")) {
			missingDeps.push(candidate[0]);
		}
	}
	if (missingDeps.length > 0) {
		throw new Error(
			`python found but numpy/Pillow are missing: ${missingDeps.join(", ")}. ` +
				"Run `pip install numpy pillow` for that interpreter, or point GTA_TOOLS_PYTHON at a python that has them.",
		);
	}
	throw new Error("no working python found; set GTA_TOOLS_PYTHON to a python executable");
}

async function run(argv, timeoutMs = 600000) {
	const python = await resolvePython();
	const { error, stdout, stderr } = await spawnOnce(python, ["-m", "gtatools.cli", ...argv], timeoutMs);
	const text = [stdout, stderr].filter((p) => p && p.trim().length > 0).join("\n").trim();
	if (error && text.length === 0) throw new Error(`gtatools failed: ${error.message}`);
	return text;
}

const clip = (text) => (text.length <= MAX_CHARS ? text : `${text.slice(0, MAX_CHARS)}\n… truncated ${text.length - MAX_CHARS} chars`);

const textOutput = {
	schema: { type: "string" },
	render: (_args, value) => [{ type: "text", text: String(value) }],
};

function stringProp(description, extra = {}) {
	return { type: "string", description, ...extra };
}

function tool(name, description, properties, required, execute) {
	return {
		name,
		description,
		parameters: { type: "object", properties, required, additionalProperties: false },
		output: textOutput,
		execute,
	};
}

export function apply(ctx) {
	const texconvArg = () => {
		const value = texconvPath();
		return value.length > 0 ? ["--texconv", value] : [];
	};

	ctx.tools.register(
		tool(
			"gta_badge_normal",
			"Generate a tangent-space normal map from a GTA V badge diffuse texture (DDS) and write it next to --out. Relief comes from luminance so engraved lettering keeps its shape; the atlas margin stays flat so no rectangle shows around the text.",
			{
				source: stringProp("DDS file or directory of DDS files to convert"),
				out: stringProp("Output directory for the generated normal maps"),
				strength: { type: "number", description: "Relief strength: flat decals 8-10, chrome art 4-5, text 6-7. Default 6.5" },
				blur: { type: "number", description: "Gaussian pre-blur on the height field. Default 1.2" },
				fmt: { type: "string", enum: ["DXT5", "DXT1", "BC5", "A8R8G8B8"], description: "Output format. Default DXT5" },
				sheet: stringProp("Optional path for a before/after contact sheet"),
			},
			["source", "out"],
			async (args) => {
				const argv = ["normals", args.source, "--out", args.out, ...texconvArg()];
				if (args.strength !== undefined) argv.push("--strength", String(args.strength));
				if (args.blur !== undefined) argv.push("--blur", String(args.blur));
				if (args.fmt !== undefined) argv.push("--fmt", args.fmt);
				if (args.sheet !== undefined) argv.push("--sheet", args.sheet);
				return clip(await run(argv));
			},
		),
	);

	ctx.tools.register(
		tool(
			"gta_ymt_audit",
			"Audit a CPedVariationInfo .ymt.xml against vanilla GTA ped rules: numAvailTex equals the sum of aTexData over the component's drawables, one compInfos entry per (slot, drawable), dangling declarations flagged. Returns a table plus a problem list.",
			{
				xml: stringProp("Path to an exported ped .ymt.xml"),
				json: stringProp("Optional path to also write findings as JSON"),
			},
			["xml"],
			async (args) => {
				const argv = ["audit", args.xml];
				if (args.json !== undefined) argv.push("--json", args.json);
				return clip(await run(argv, 120000));
			},
		),
	);

	ctx.tools.register(
		tool(
			"gta_ytd_scale",
			"Rescale DDS textures for GTA V texture dictionaries, keeping the original pixel format and mip depth. RGB and alpha are resized separately so Pillow's premultiplied-alpha darkening is avoided.",
			{
				path: stringProp("DDS file or directory (recursive)"),
				out: stringProp("Output directory; the input layout is mirrored"),
				longEdge: { type: "integer", description: "Target long edge in pixels. Default 1536" },
				minEdge: { type: "integer", description: "Skip files whose long edge is at or below this. Default 1025" },
			},
			["path", "out"],
			async (args) => {
				const argv = ["scale", args.path, "--out", args.out, ...texconvArg()];
				if (args.longEdge !== undefined) argv.push("--long-edge", String(args.longEdge));
				if (args.minEdge !== undefined) argv.push("--min-edge", String(args.minEdge));
				return clip(await run(argv));
			},
		),
	);

	ctx.tools.register(
		tool(
			"gta_ytd_pack",
			"Build a gen9 YTD from a CodeWalker ytd.xml plus a folder of DDS files. Passing original restores the gen9 render-target descriptor bits by texture name; without it scripted render targets such as dashboard dials break in game.",
			{
				xml: stringProp("Path to the TextureDictionary XML"),
				build: stringProp("Folder holding the DDS files named by the XML"),
				out: stringProp("Output .ytd path"),
				original: stringProp("Existing YTD to copy gen9 descriptors from"),
			},
			["xml", "build", "out"],
			async (args) => {
				const argv = ["pack", "--xml", args.xml, "--build", args.build, "--out", args.out];
				if (args.original !== undefined) argv.push("--original", args.original);
				const core = coreDir();
				if (core.length > 0) argv.push("--core-dir", core);
				return clip(await run(argv));
			},
		),
	);
}
