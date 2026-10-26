#!/bin/bash
#SBATCH --job-name=pcbmotor
#SBATCH --partition=ada
#SBATCH --nodes=1 --ntasks=32
#SBATCH --mem-per-cpu=7800M
#SBATCH --time=100:00:00
#SBATCH --output=pcbmotor_%j.out
#SBATCH --account=eleceng
#SBATCH --mail-user=YOUR_EMAIL@myuct.ac.za --mail-type=END,FAIL
''':'
# ---- bash part: load modules, then hand this same file to Python -----------------------------------------
if ! type module >/dev/null 2>&1; then
  for f in /etc/profile.d/modules.sh /usr/share/Modules/init/bash /etc/profile.d/lmod.sh; do [ -f "$f" ] && . "$f"; done
fi
module load python/miniconda3-py3.12 >/dev/null 2>&1 || true
module load software/ansys-2025R2-v252 >/dev/null 2>&1 || true
PY=$(command -v python3 || command -v python)
exec "$PY" "$0" "$@"
'''
# -*- coding: utf-8 -*-
"""
hpc_motor.py - full-motor Maxwell solves of the Rev0, Rev1-S, Rev1-D and Rev2-S PCB axial-flux motors on the UCT HPC.
EEE4022S AK-07. One self-contained file: it carries the lab pipeline (rev0_v9), the board geometry and the
reference results inside it.

HOW TO RUN (from the login node, in the folder where this file is):
    sbatch hpc_motor.py --mode smoke                        ~1 h: AEDT, licence, cores, one-board static + transient
    sbatch hpc_motor.py --mode friday --motor Rev0          Rev0: 2-angle static, mesh gates, rotating runs (32 cores)
    sbatch hpc_motor.py --mode friday --motor Rev1S         Rev1-S: same, two rotating bands (resubmits itself at 40 cores)
    sbatch hpc_motor.py --mode friday --motor Rev2S         Rev2-S (optional): 2-angle static only, 40 cores
    sbatch hpc_motor.py --mode friday --motor ALL           Rev0 here + Rev1-S in its own 40-core job
    python3 hpc_motor.py --mode status            progress of every motor (safe on the login node)
    python3 hpc_motor.py --mode report            rebuild the reports from what has finished
(If you type "python3 hpc_motor.py --mode full" on the login node by mistake, it submits itself with sbatch -
 it never runs AEDT on the login node.)

Everything is written under the work folder (default /scratch/$USER/pcbmotor_hpc, or ~/pcbmotor_hpc):
    RESULTS.txt / RESULTS.json      the answer: K per motor vs the field map and the board-by-board sum
    <motor>/supervisor.log          what happened, step by step, including every retry and why
    <motor>/state.json              the checkpoint the next job resumes from
    <motor>/results/                per-motor summary, angle table, per-board table

What it does on its own:
  * resumes from checkpoints after any crash, kill or time-out (board by board, stage by stage, angle by angle)
  * AEDT runs in a child process; a crash, freeze or out-of-memory kills only the child, never the supervisor
  * memory guard: stops AEDT cleanly before SLURM's memory limit would kill the whole job
  * steps down a solver ladder when a solve runs out of memory (direct -> iterative -> fewer passes)
  * resubmits itself before the wall-time limit and carries on from the checkpoint
  * retries licence and start-up failures with back-off; switches to PyAEDT if the AEDT script engine fails
  * checks every solved angle (solver errors, missing exports, rotor vs copper torque) before accepting it
  * disk guard: keeps the work folder inside --disk-gb (UCT /scratch quota 50 GB), deletes the short-step
    gate projects, sizes the saved field frames to fit, puts AEDT temp files on the node's local disk
  * at most 40 cores per job (UCT limit); a Rev1/Rev2 job started with too few cores resubmits itself
"""

import argparse
import base64
import fcntl
import glob
import hashlib
import io
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time

VERSION = "1.0 (2026-10-11)"
MOTORS = ["Rev0", "Rev1S", "Rev1D", "Rev2S"]
ALL_MOTORS = ["Rev0", "Rev1S"]          # --motor ALL: the priority pair (decided 13 Oct); Rev1D / Rev2S by name
MOTOR_TEXT = {"Rev0": "Rev0 (S1-R1, 16 magnets)", "Rev1S": "Rev1-S (S1-R1-S2-R2, 32 magnets)",
              "Rev1D": "Rev1-D (S1-R1(PM/Fe/PM)-S2-R2, 48 magnets)",
              "Rev2S": "Rev2-S (S1-R1-S2-R2-S3-R3, 48 magnets)"}
FROZEN_TAG = {"Rev0": "REV0", "Rev1S": "REV1S", "Rev1D": "REV1D", "Rev2S": "REV2S"}
RIPPLE_PERIOD_DEG = 7.5           # 16 poles: torque ripple period = 360 / (6 * 8) deg mech
AEDT_PREFERENCE = ["v252", "v261", "v251", "v242", "v241"]
MODULES = ["software/ansys-2025R2-v252", "software/ansys-2026R1-v261", "software/ansys-2025R1-v251",
           "software/ansys-2024R2-v242"]

# Solver ladder. A solve that runs out of memory (or dies while solving) moves one step down; the level that
# worked becomes the starting level for the remaining angles of that motor.
LEVELS = [
    {"name": "L0 direct, 8 passes", "iterative": False, "max_passes": 8, "refine": 25, "error": 0.5},
    {"name": "L1 iterative, 8 passes", "iterative": True, "max_passes": 8, "refine": 25, "error": 0.5},
    {"name": "L2 iterative, 6 passes", "iterative": True, "max_passes": 6, "refine": 20, "error": 1.0},
    {"name": "L3 iterative, 4 passes", "iterative": True, "max_passes": 4, "refine": 20, "error": 1.0},
    {"name": "L4 iterative, 3 passes", "iterative": True, "max_passes": 3, "refine": 15, "error": 2.0},
    {"name": "L5 iterative, 2 passes (lab attempt)", "iterative": True, "max_passes": 2, "refine": 20, "error": 2.0},
]
PILOT_LEVEL = 4

# Tunables (environment variables override, mostly for testing)
POLL_S = float(os.environ.get("HPCM_POLL_S", "10"))
MEM_FRACTION = float(os.environ.get("HPCM_MEM_FRACTION", "0.92"))
WALL_MARGIN_S = float(os.environ.get("HPCM_WALL_MARGIN_S", "900"))
HANG_S = {"probe": 1200, "smoke": 3600, "stator": 3600, "final": 3600, "solve": 5400, "tgate": 3600,
          "trot": 5400, "tprep": 3600, "trun": 5400, "lab": 5400}
if os.environ.get("HPCM_HANG_S"):
    HANG_S = dict((k, float(os.environ["HPCM_HANG_S"])) for k in HANG_S)
BACKOFF_S = [float(x) for x in os.environ.get("HPCM_BACKOFF_S", "60,300,600,1200,1800").split(",")]
EST_S = {"probe": 900, "smoke": 2700, "stator": 4 * 3600, "final": 2 * 3600, "solve": 8 * 3600, "tgate": 1800,
         "trot": 3600, "tequiv": 8 * 3600, "tprep": 3600, "tstep": 3 * 3600, "tprod": 30 * 3600}
TRANSIENT_SPP = {"Rev0": 90, "Rev1S": 45, "Rev1D": 45, "Rev2S": 45}   # target time steps per electrical period
TSTEP_TOL_PCT, TSTEP_MAX_PCT = 3.0, 6.0                  # short-step torque vs converged static torque
EQUIV_TOL_PCT, EQUIV_MAX_PCT = 0.5, 1.5                  # Rev1 split-shaft vs united-shaft static torque
R_BOARD_PHASE = 0.2656                                   # ohm, DC resistance per board and phase (lab, traces)
FATAL_KINDS = ("stator", "final", "probe", "smoke")      # the T0 transient gates must all report, so not fatal


def task_kind(tid):
    if tid == "lab":
        return "lab"
    for pre, k in (("pilot_", "pilot"), ("solve_", "solve"), ("tstep_", "tstep"), ("tprod_", "tprod")):
        if tid.startswith(pre):
            return k
    return tid
MAX_RESUBMITS = int(os.environ.get("HPCM_MAX_RESUBMITS", "2"))   # default; --max-resubmits overrides
MAX_ATTEMPTS = 14

# Retry policy per failure kind: ("same", n) = retry at the same level up to n times;
# ("down", n) = for solves step down the ladder (n same-level retries first); ("fail", 0) = give up now.
POLICY = {
    "license": ("same", 8), "launch": ("same", 5), "lock": ("same", 3),
    "oom": ("down", 0), "solve_oom": ("down", 0), "hang": ("down", 1), "crash": ("down", 1),
    "solve_error": ("down", 1), "export_error": ("same", 1), "python_error": ("same", 1),
    "build_error": ("same", 1), "model_mismatch": ("fail", 0), "disk": ("fail", 0),
}
LAB_PROFILES = ["FMROT_REV0_SHORT", "FMROT_REV0", "FMROT_REV1S_SHORT", "FMROT_REV1S", "EQ_REV0_CAL", "EQ_REV0_ROT_SHORT",
                "EQ_REV0_ROT", "EQ_REV1S_CAL", "EQ_REV1S_ROT_SHORT", "EQ_REV1S_ROT"]   # --mode lab --motor <profile>
EST_LAB_S = 30 * 3600
MAX_CORES_JOB = int(os.environ.get("HPCM_MAX_CORES_JOB", "40"))   # UCT HPC: 40 cores per job, 1 node per job
DISK_CHECK_S = float(os.environ.get("HPCM_DISK_CHECK_S", "120"))
FIELD_FRAMES = 15                                                   # saved field frames per production run (max)


# ============================================================================================ small helpers
def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def hms(s):
    if s is None or s == float("inf"):
        return "unlimited"
    s = int(max(0, s))
    return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)


def atomic_json(path, obj):
    tmp = "%s.tmp%d" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=str)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


class Log(object):
    def __init__(self, path=None):
        self.path = path

    def __call__(self, msg, level="INFO"):
        line = "%s [%s] %s" % (now(), level, msg)
        print(line, flush=True)
        if self.path:
            try:
                with open(self.path, "a") as f:
                    f.write(line + "\n")
            except Exception:
                pass


LOG = Log()


def sh(cmd, timeout=60, env=None):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, env=env, universal_newlines=True)
        return r.returncode, r.stdout
    except Exception as e:
        return 127, str(e)


# ============================================================================================ payload
def payload_bytes():
    return base64.b64decode(PAYLOAD_B64.encode("ascii"))


def extract_payload(work):
    data = payload_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != PAYLOAD_SHA256:
        raise SystemExit("Embedded payload is corrupt (sha256 mismatch) - re-copy hpc_motor.py to the cluster")
    code = os.path.join(work, "code_" + sha[:10])
    if not os.path.isfile(os.path.join(code, ".complete")):
        tmp = code + ".tmp%d" % os.getpid()
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for m in tf.getmembers():
                if m.name.startswith("/") or ".." in m.name.split("/"):
                    raise SystemExit("unsafe path in payload: %s" % m.name)
            try:
                tf.extractall(tmp, filter="data")
            except TypeError:
                tf.extractall(tmp)
        open(os.path.join(tmp, ".complete"), "w").write(sha)
        shutil.rmtree(code, ignore_errors=True)
        os.replace(tmp, code)
    return code


def source_check(code):
    """The embedded board geometry still matches the Altium/ODB++ source package (vias, pads, NPTH)."""
    sys.path.insert(0, code)
    try:
        import pcb_geometry
        g = pcb_geometry.load()
    finally:
        sys.path.pop(0)
    out, bad = [], []
    src = read_json(os.path.join(code, "source_check.json"), {})
    if not src:
        return ["source package extract missing - check skipped"], []

    def near(a, pts, tol=0.002):
        return any(abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol for b in pts)
    vias_src = [(v["x"], v["y"], v["net"]) for v in src["vias"]]
    vias_emb = [(v["x"], v["y"], v["net"]) for v in g["vias"]]
    uniq = []
    for v in vias_src:
        if not any(abs(v[0] - u[0]) < 1e-4 and abs(v[1] - u[1]) < 1e-4 and v[2] == u[2] for u in uniq):
            uniq.append(v)
    miss = [v for v in uniq if not near(v, [(w[0], w[1]) for w in vias_emb if w[2] == v[2]])]
    extra = [v for v in vias_emb if not near(v, [(w[0], w[1]) for w in uniq if w[2] == v[2]])]
    out.append("vias: source %d records (%d unique) vs embedded %d -> %d missing, %d extra"
               % (len(vias_src), len(uniq), len(vias_emb), len(miss), len(extra)))
    if miss or extra or len(uniq) != len(vias_emb):
        bad.append("via mismatch")
    pads_src = [(p["x"], p["y"], p["net"]) for p in src["pads"]]
    pmiss = [p for p in pads_src if not near(p, [(q["x"], q["y"]) for q in g["pads"] if q["net"] == p[2]])]
    out.append("terminal pads: source %d vs embedded %d -> %d missing" % (len(pads_src), len(g["pads"]), len(pmiss)))
    if pmiss or len(pads_src) != len(g["pads"]):
        bad.append("pad mismatch")
    hmiss = [h for h in src["npth"] if not near((h["x"], h["y"]), [(q["x"], q["y"]) for q in g["npth"]])]
    out.append("mounting holes: source %d vs embedded %d -> %d missing" % (len(src["npth"]), len(g["npth"]), len(hmiss)))
    if hmiss or len(src["npth"]) != len(g["npth"]):
        bad.append("NPTH mismatch")
    return out, bad


# ============================================================================================ machine facts
def cgroup_paths():
    v2, v1 = None, None
    try:
        for line in open("/proc/self/cgroup"):
            parts = line.strip().split(":", 2)
            if len(parts) != 3:
                continue
            if parts[0] == "0" and parts[1] == "":
                v2 = "/sys/fs/cgroup" + parts[2]
            elif "memory" in parts[1].split(","):
                v1 = "/sys/fs/cgroup/memory" + parts[2]
    except Exception:
        pass
    return v2, v1


def _read_num(path):
    try:
        s = open(path).read().strip()
        if s in ("max", "") or not s.isdigit():
            return None
        v = int(s)
        return v if v < (1 << 60) else None
    except Exception:
        return None


def memory_limit():
    """Bytes this job may use: the tightest of cgroup, SLURM allocation and physical RAM."""
    cands = {}
    if os.environ.get("HPCM_MEM_LIMIT_GB"):
        return float(os.environ["HPCM_MEM_LIMIT_GB"]) * 2 ** 30, {"override": True}
    v2, v1 = cgroup_paths()
    p = v2
    while p and p.startswith("/sys/fs/cgroup") and len(p) > len("/sys/fs/cgroup"):
        n = _read_num(os.path.join(p, "memory.max"))
        if n:
            cands["cgroup_v2"] = n
            break
        p = os.path.dirname(p)
    if v1:
        n = _read_num(os.path.join(v1, "memory.limit_in_bytes"))
        if n:
            cands["cgroup_v1"] = n
    mpn = os.environ.get("SLURM_MEM_PER_NODE")
    mpc = os.environ.get("SLURM_MEM_PER_CPU")
    ncpu = os.environ.get("SLURM_CPUS_ON_NODE") or os.environ.get("SLURM_NTASKS")
    if mpn and mpn.isdigit():
        cands["slurm_per_node"] = int(mpn) * 2 ** 20
    elif mpc and mpc.isdigit() and ncpu and ncpu.isdigit():
        cands["slurm_per_cpu"] = int(mpc) * int(ncpu) * 2 ** 20
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                cands["physical"] = int(line.split()[1]) * 1024
    except Exception:
        pass
    return (min(cands.values()) if cands else 16 * 2 ** 30), cands


def oom_kills():
    v2, v1 = cgroup_paths()
    for path in ([os.path.join(v2, "memory.events")] if v2 else []) + ([os.path.join(v1, "memory.oom_control")] if v1 else []):
        try:
            for line in open(path):
                if line.startswith("oom_kill "):
                    return int(line.split()[1])
        except Exception:
            pass
    return None


def cores():
    for k in ("HPCM_CORES", "SLURM_CPUS_ON_NODE", "SLURM_NTASKS", "SLURM_CPUS_PER_TASK"):
        v = os.environ.get(k)
        if v and v.split("(")[0].isdigit():
            return int(v.split("(")[0])
    try:
        return len(os.sched_getaffinity(0))
    except Exception:
        return os.cpu_count() or 1


def _parse_slurm_time(s):
    s = s.strip()
    if not s or s.upper() in ("UNLIMITED", "INVALID", "NOT_SET"):
        return None
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return days * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def wall_deadline():
    """Epoch seconds when SLURM will stop this job (inf when not under SLURM)."""
    if os.environ.get("HPCM_WALL_SECONDS"):
        return time.time() + float(os.environ["HPCM_WALL_SECONDS"])
    jid = os.environ.get("SLURM_JOB_ID")
    if not jid:
        return float("inf")
    rc, out = sh(["squeue", "-h", "-j", jid, "-o", "%L"], timeout=30)
    if rc == 0 and out.strip():
        left = _parse_slurm_time(out.strip().splitlines()[-1])
        if left:
            return time.time() + left
    rc, out = sh(["scontrol", "show", "job", jid], timeout=30)
    m = re.search(r"TimeLimit=(\S+)", out or "")
    if m:
        lim = _parse_slurm_time(m.group(1))
        if lim:
            return time.time() + lim - 60
    return time.time() + 100 * 3600


# ============================================================================================ AEDT discovery
def module_env(mod):
    """Environment after 'module load <mod>' (modules are a shell function; ask bash)."""
    init = ("for f in /etc/profile.d/modules.sh /usr/share/Modules/init/bash /etc/profile.d/lmod.sh; "
            "do [ -f $f ] && . $f; done; ")
    rc, out = sh(["bash", "-c", init + "module load %s >/dev/null 2>&1 && env -0" % shlex.quote(mod)], timeout=120)
    if rc != 0 or "\0" not in out:
        return None
    env = {}
    for item in out.split("\0"):
        if "=" in item:
            k, v = item.split("=", 1)
            env[k] = v
    return env


def _aedt_in_env(env):
    cands = []
    for d in (env.get("PATH") or "").split(os.pathsep):
        p = os.path.join(d, "ansysedt")
        if d and os.path.isfile(p) and os.access(p, os.X_OK):
            cands.append(p)
    for k, v in env.items():
        m = re.match(r"ANSYSEM_ROOT(\d+)$", k)
        if m:
            p = os.path.join(v, "ansysedt")
            if os.path.isfile(p):
                cands.append(p)
    return cands


def _rank(path):
    for i, tag in enumerate(AEDT_PREFERENCE):
        if tag in path:
            return i
    return len(AEDT_PREFERENCE)


def find_aedt():
    """-> (path to ansysedt, environment for it, how it was found)."""
    env = dict(os.environ)
    if env.get("HPCM_AEDT"):
        return env["HPCM_AEDT"], env, "HPCM_AEDT"
    found = _aedt_in_env(env)
    if found:
        return sorted(found, key=_rank)[0], env, "already on PATH / ANSYSEM_ROOT"
    for mod in MODULES:
        e = module_env(mod)
        if e:
            f = _aedt_in_env(e)
            if f:
                return sorted(f, key=_rank)[0], e, "module load %s" % mod
    pats = ["/opt/exp_soft/*/v2*/AnsysEM/ansysedt", "/opt/exp_soft/*/*/v2*/AnsysEM/ansysedt",
            "/opt/exp_soft/*/ansys_inc/v2*/AnsysEM/ansysedt", "/opt/exp_soft/*/*/ansys_inc/v2*/AnsysEM/ansysedt",
            "/usr/ansys_inc/v2*/AnsysEM/ansysedt", "/opt/ansys_inc/v2*/AnsysEM/ansysedt"]
    hits = []
    for p in pats:
        hits += [h for h in glob.glob(p) if os.access(h, os.X_OK)]
    if hits:
        best = sorted(hits, key=_rank)[0]
        m = re.search(r"v(\d{3})", best)
        if m:
            env["ANSYSEM_ROOT%s" % m.group(1)] = os.path.dirname(best)
        return best, env, "file search"
    return None, env, "not found"


def aedt_version_tag(path):
    m = re.search(r"v(\d)(\d)(\d)", path or "")
    return ("20%s%s.%s" % (m.group(1), m.group(2), m.group(3))) if m else None


# ============================================================================================ processes
def _proc_table():
    t = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % d) as f:
                s = f.read()
            rest = s[s.rindex(")") + 2:].split()
            t[int(d)] = {"ppid": int(rest[1]), "sid": int(rest[3]), "cpu": int(rest[11]) + int(rest[12])}
        except Exception:
            continue
    return t


def _rss(pid):
    try:
        for line in open("/proc/%d/status" % pid):
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


def _lineage():
    """This supervisor and its ancestors (never to be counted or killed)."""
    out, p = set(), os.getpid()
    while p > 1 and p not in out:
        out.add(p)
        try:
            s = open("/proc/%d/stat" % p).read()
            p = int(s[s.rindex(")") + 2:].split()[1])
        except Exception:
            break
    return out


def _job_pids():
    """Processes in this SLURM job's cgroup (catches solver engines that detach from AEDT's process tree)."""
    jid = os.environ.get("SLURM_JOB_ID")
    if not jid:
        return set()
    tag, me, out = "job_%s" % jid, os.getuid(), set()
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            if os.stat("/proc/" + d).st_uid != me:
                continue
            if tag in open("/proc/%s/cgroup" % d).read():
                out.add(int(d))
        except Exception:
            continue
    return out - _lineage()


def tree(root):
    """root + all descendants + anything in root's session + the rest of this SLURM job (one AEDT at a time)."""
    t = _proc_table()
    out = set([root]) if root in t else set()
    changed = True
    while changed:
        changed = False
        for pid, d in t.items():
            if pid not in out and (d["ppid"] in out or d["sid"] == root):
                out.add(pid)
                changed = True
    out |= set(p for p in _job_pids() if p in t and _state(p) != "Z")
    return out, t


def kill_tree(root, grace=20):
    pids, _ = tree(root)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(root, sig)
        except Exception:
            pass
        for p in list(pids):
            try:
                os.kill(p, sig)
            except Exception:
                pass
        end = time.time() + (grace if sig == signal.SIGTERM else 5)
        while time.time() < end:
            alive = [p for p in pids if os.path.exists("/proc/%d" % p) and _state(p) != "Z"]
            if not alive:
                break
            time.sleep(0.5)
        pids = pids | tree(root)[0]


def _state(pid):
    try:
        s = open("/proc/%d/stat" % pid).read()
        return s[s.rindex(")") + 2]
    except Exception:
        return "X"


def newest_mtime(paths):
    m = 0.0
    for top in paths:
        if not os.path.isdir(top):
            continue
        for root, dirs, files in os.walk(top):
            for fn in files:
                try:
                    m = max(m, os.path.getmtime(os.path.join(root, fn)))
                except Exception:
                    pass
    return m


def dir_size(top):
    """Bytes used under a folder (files only; links not followed)."""
    n = 0
    if os.path.isfile(top):
        return os.path.getsize(top)
    for root, dirs, files in os.walk(top):
        for fn in files:
            try:
                n += os.lstat(os.path.join(root, fn)).st_size
            except Exception:
                pass
    return n


_QUOTA = {"t": 0.0, "v": None}


def _size_bytes(txt):
    m = re.match(r"^([\d.]+)\s*([KMGTP]?)i?B?$", txt.strip(), re.I)
    if not m:
        return None
    return float(m.group(1)) * 1024.0 ** "BKMGTP".index((m.group(2) or "B").upper())


def scratch_quota():
    """(limit, used) bytes of this user's /scratch quota from the UCT 'quota' command (cached 5 min), or None."""
    if time.time() - _QUOTA["t"] < 300:
        return _QUOTA["v"]
    _QUOTA["t"] = time.time()
    val = None
    # UCT: 'quota' and 'myquota' are login-shell aliases of 'purequota' (not visible inside a batch job)
    for cmd in (["/scratch/slurm/bin/purequota"], ["purequota"], ["bash", "-lc", "purequota"], ["myquota"], ["quota"]):
        try:
            out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                                 universal_newlines=True).stdout
        except Exception:
            continue
        for line in out.splitlines():
            f = line.split()
            if len(f) >= 3 and f[0].rstrip("/") == "/scratch":
                lim, used = _size_bytes(f[1]), _size_bytes(f[2])
                if lim and used is not None:
                    val = (lim, used)
        if val:
            break
    _QUOTA["v"] = val
    return val


def pick_tmp(work, job):
    """AEDT scratch (TMPDIR): the job's own temporary folder when SLURM / the cluster provides one
    (SLURM_TMPDIR, or a job-specific TMPDIR), otherwise a folder inside the work folder on /scratch, which the
    disk guard counts. Generic shared locations such as /tmp are never picked."""
    for var in ("SLURM_TMPDIR", "TMPDIR"):
        base = os.environ.get(var)
        if not base or os.path.abspath(base).rstrip("/") in ("/tmp", "/var/tmp", "/dev/shm"):
            continue
        if not os.path.isdir(base) or not os.access(base, os.W_OK):
            continue
        if os.path.abspath(base).startswith(os.path.abspath(work)):
            continue
        d = os.path.join(base, "hpcm_%s" % job)
        try:
            if not os.path.isdir(d):
                os.makedirs(d)
            return d, "job temporary folder from the scheduler ($%s = %s)" % (var, base)
        except Exception:
            continue
    d = os.path.join(work, "tmp")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d, "work folder on /scratch (no job-specific temporary folder provided; counted by the disk guard)"


def decide(task_kind, err_kind, same_fail, level, attempts):
    """-> ("retry", level) or ("fail", level). same_fail counts failures at the current level."""
    pol, n_same = POLICY.get(err_kind, ("same", 1))
    is_solve = task_kind in ("solve", "pilot", "tequiv")
    if task_kind in ("tstep", "tprod", "lab") and err_kind in ("oom", "solve_oom"):
        return "fail", level          # a fixed transient mesh cannot step down; the mesh ladder goes the other way
    if task_kind in ("tstep", "tprod", "lab") and err_kind in ("crash", "hang", "solve_error", "export_error"):
        return ("retry", level) if same_fail <= 1 else ("fail", level)   # long runs: one retry, then salvage
    if pol == "fail" or attempts >= MAX_ATTEMPTS:
        return "fail", level
    if same_fail <= n_same:
        return "retry", level
    if pol == "down":
        if is_solve:
            return ("retry", level + 1) if level + 1 < len(LEVELS) else ("fail", level)
        return ("retry", level) if same_fail <= 3 else ("fail", level)
    return "fail", level


# ============================================================================================ the supervisor
class Supervisor(object):
    def __init__(self, args, work, code):
        self.a = args
        self.work = work
        self.code = code
        self.cores = cores()
        self.mem_limit, self.mem_sources = memory_limit()
        self.deadline = wall_deadline()
        self.job = os.environ.get("SLURM_JOB_ID", "local-%d" % os.getpid())
        self.refs = read_json(os.path.join(code, "references.json"), {})
        self.aedt = None
        self.aedt_env = None

    # ------------------------------------------------------------------ setup
    def discover(self):
        exe, env, how = find_aedt()
        if not exe:
            LOG("AEDT (ansysedt) not found: tried PATH, ANSYSEM_ROOT*, module load %s, /opt/exp_soft search"
                % ", ".join(MODULES), "ERROR")
            return False
        self.aedt = exe
        env = dict(env)
        env.setdefault("ANS_NODEPCHECK", "1")
        tmp, where = pick_tmp(self.work, self.job)
        self.tmpdir = tmp
        if where.startswith("job temporary"):
            import atexit
            atexit.register(shutil.rmtree, tmp, True)          # leave the node's disk as we found it
        LOG("AEDT temp folder (TMPDIR): %s - %s" % (tmp, where))
        env["TMPDIR"] = tmp
        env["OMP_NUM_THREADS"] = str(self.cores)
        env["MKL_NUM_THREADS"] = str(self.cores)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.aedt_env = env
        lic = [k + "=" + env[k] for k in env if "LICENSE" in k.upper() or k.upper().startswith("ANSYSLI")]
        LOG("AEDT: %s (found via %s, version %s); licence settings: %s"
            % (exe, how, aedt_version_tag(exe) or "?", "; ".join(lic) or "none in the environment (AEDT default)"))
        return True

    def banner(self, motor, mode):
        lim_gb = self.mem_limit / 2.0 ** 30
        LOG("hpc_motor %s | job %s | node %s | motor %s | mode %s" % (VERSION, self.job, os.uname()[1], motor, mode))
        LOG("Resources: %d cores, memory limit %.1f GB (%s), wall time left %s"
            % (self.cores, lim_gb, ", ".join("%s %.1f GB" % (k, v / 2.0 ** 30) for k, v in self.mem_sources.items()),
               hms(self.deadline - time.time())))
        q = scratch_quota()
        LOG("Work folder: %s (disk budget %.1f GB for the whole work folder; now used %.1f GB). /scratch quota: %s"
            % (self.work, self.a.disk_gb, self.disk_used() / 2.0 ** 30,
               ("%.1f of %.0f GB used (all your files)" % (q[1] / 2.0 ** 30, q[0] / 2.0 ** 30)) if q else
               "'quota' not readable here - the work-folder budget is used alone"))

    def disk_used(self):
        return dir_size(self.work)

    def disk_left(self):
        """Bytes left in the budget (--disk-gb, all motors share the work folder) and on the file system."""
        left = self.a.disk_gb * 2.0 ** 30 - self.disk_used()
        try:
            left = min(left, shutil.disk_usage(self.work).free)
        except Exception:
            pass
        q = scratch_quota()          # the quota is per user for the whole /scratch volume, not per folder
        if q and os.path.abspath(self.work).startswith("/scratch"):
            left = min(left, q[0] - q[1] - (50.0 - self.a.disk_gb) * 2 ** 30)
        return left

    def clean_tstep(self, motor, mesh_level):
        """Short-step projects are only for the gate: note their size (the production field-frame estimate),
        then delete the project and solution files. The exported CSVs are kept."""
        tdir = os.path.join(self.mdir(motor), "aedt", "transient")
        tag = "_TSTEP_MT%d" % mesh_level
        size, gone = 0, []
        if os.path.isdir(tdir):
            for fn in os.listdir(tdir):
                base = fn.split(".aedt")[0]
                if base.endswith(tag) and ".aedt" in fn:
                    pth = os.path.join(tdir, fn)
                    size += dir_size(pth)
                    try:
                        shutil.rmtree(pth) if os.path.isdir(pth) else os.remove(pth)
                        gone.append(fn)
                    except Exception:
                        pass
        if gone:
            LOG("[%s] short-step MT%d project used %.2f GB - deleted (%s); its CSVs are kept"
                % (motor, mesh_level, size / 2.0 ** 30, ", ".join(sorted(gone))))
        return size

    # ------------------------------------------------------------------ state
    def mdir(self, motor):
        d = os.path.join(self.work, motor)
        for sub in ("", "tasks", "results", "aedt"):
            p = os.path.join(d, sub)
            if not os.path.isdir(p):
                os.makedirs(p)
        return d

    def load_state(self, motor):
        p = os.path.join(self.mdir(motor), "state.json")
        st = read_json(p)
        if not st:
            st = {"motor": motor, "created": now(), "tasks": {}, "level_floor": 0, "resubmits": 0,
                  "launch_mode": "script", "jobs": [], "launch_failures": 0}
        return st

    def save_state(self, motor, st):
        st["updated"] = now()
        atomic_json(os.path.join(self.mdir(motor), "state.json"), st)

    # ------------------------------------------------------------------ task plan
    def thetas(self, n):
        return [round(RIPPLE_PERIOD_DEG * i / n, 6) for i in range(n)]

    def angle_order(self, n):
        """0, then halves, quarters ... so a run stopped early still spans the ripple period."""
        order, step = [0], n
        while len(order) < n:
            step = max(1, step // 2)
            for i in range(0, n, step):
                if i not in order:
                    order.append(i)
        return order

    def plan(self, motor, mode):
        """Separate simulation stages; each later stage only runs after the checks of the earlier ones."""
        if mode == "smoke":
            return [("probe", {}), ("smoke", {}), ("tgate", {}), ("trot", {})]
        if mode == "lab":
            return [("lab", {"profile": motor})]
        tasks = [("stator", {}), ("final", {"motor": motor})]
        th = self.thetas(self.a.angles)
        if mode == "pilot":
            tasks.append(("pilot_00", {"motor": motor, "angle_index": 0, "theta_deg": 0.0}))
        if mode in ("static", "full", "friday"):
            for i in self.angle_order(self.a.angles):
                tasks.append(("solve_%02d" % i, {"motor": motor, "angle_index": i, "theta_deg": th[i]}))
        if mode == "transient":
            tasks.append(("solve_00", {"motor": motor, "angle_index": 0, "theta_deg": 0.0}))
        if mode in ("transient", "full") or (mode == "friday" and motor in ("Rev0", "Rev1S")):
            if motor != "Rev0":
                tasks.append(("tequiv", {"motor": motor, "angle_index": 90, "theta_deg": 0.0, "split_shaft": True}))
            tasks.append(("tprep", {"motor": motor}))
            for k in range(3):
                tasks.append(("tstep_mt%d" % k, {"motor": motor, "mesh_level": k}))
            if self.a.tr_runs in ("both", "noload"):
                tasks.append(("tprod_noload", {"motor": motor, "ipk": 0.0}))
            if self.a.tr_runs in ("both", "load"):
                tasks.append(("tprod_load", {"motor": motor, "ipk": float(self.a.ipk)}))
        return tasks

    # ------------------------------------------------------------------ stage dependencies and gates
    def prepare(self, motor, st, tid, kind, params):
        """-> (params, None) to run, or (None, why) to skip/fail without running."""
        T = st["tasks"]
        p = dict(params)
        p.setdefault("motor", motor)
        p["rpm"] = float(self.a.rpm)
        p["psi_deg"] = float(self.refs.get("baseline", {}).get("psi_deg", -30.181))
        gates = st.setdefault("gates", {})
        if kind == "lab":
            p["shared_dir"] = self.lab_shared(motor)
            p.pop("rpm", None)
            p.pop("psi_deg", None)
            return p, None
        if kind == "tequiv":
            s0 = T.get("solve_00", {})
            if s0.get("status") != "done":
                return None, "needs the static solve at 0 deg (solve_00) as its reference"
            p["level_index"] = s0.get("level", 0)
        if kind in ("tprep", "tstep", "tprod"):
            if motor != "Rev0":
                g = gates.get("equiv", {})
                if g.get("verdict") not in ("PASS", "MARGINAL"):
                    return None, "split-shaft equivalence check not passed (%s)" % g.get("verdict", "not run")
            if T.get("solve_00", {}).get("status") != "done":
                return None, "needs the static solve at 0 deg (solve_00) as the reference"
        if kind in ("tstep", "tprod") and T.get("tprep", {}).get("status") != "done":
            return None, "transient base model (tprep) not built"
        if kind == "tstep":
            if st.get("tr_plan"):
                return None, "SKIP: an earlier mesh level already passed"
            prev = [g for g in gates.get("tstep", []) if g.get("verdict") == "FAIL_HARD"]
            if prev:
                return None, "SKIP: verification stopped (%s)" % prev[-1].get("why")
            p.update({"run_name": "TSTEP_MT%d" % p["mesh_level"], "steps_per_period": self.a.tr_spp or TRANSIENT_SPP[motor],
                      "n_steps": 3, "save_every": 0, "ipk": float(self.a.ipk), "no_fields": True})
        if kind == "tprod":
            plan = st.get("tr_plan")
            if not plan:
                return None, "short-step verification did not pass: %s" % (gates.get("tstep_summary") or "not run")
            p.update({"run_name": "TPROD_%s" % ("LOAD" if p["ipk"] > 0 else "NOLOAD"), "mesh_level": plan["mesh_level"],
                      "steps_per_period": plan["spp"], "n_steps": plan["n_steps"]})
            p.update(self.field_plan(motor, st, tid, plan))
        return p, None

    def field_plan(self, motor, st, tid, plan):
        """How many field frames the production run may save inside the disk budget. One saved frame is taken
        as the size of the short-step project at the same mesh (mesh + one solution - an upper bound); the
        run itself needs about one more of those. The space left is shared with the other runs still to do."""
        hist = st["tasks"].get("tstep_mt%d" % plan["mesh_level"], {}).get("history", [])
        frame = max([h.get("project_GB") or 0 for h in hist] + [0.0]) * 2 ** 30
        pending = [x for x in ("tprod_noload", "tprod_load") if st["tasks"].get(x, {}).get("status") != "done"]
        others = 1 if self.a.motor == "ALL" or len(self.running_motors()) > 1 else 0
        share = self.disk_left() / float(max(1, len(pending) + others))
        want = min(FIELD_FRAMES, plan["n_steps"])
        if frame <= 0:
            frames = want
            why = "short-step project size unknown"
        else:
            frames = int((0.8 * share - frame) // frame)
            why = "%.2f GB per frame, %.1f GB of disk for this run" % (frame / 2.0 ** 30, share / 2.0 ** 30)
        frames = max(0, min(want, frames))
        if frames < 4:
            LOG("[%s] %s: only room for %d field frames (%s) - fields NOT saved; torque, back-EMF, current and "
                "loss waveforms are still recorded" % (motor, tid, frames, why), "WARN")
            return {"save_every": 0, "no_fields": True, "field_frames": 0}
        every = max(1, int(math.ceil(plan["n_steps"] / float(frames))))
        LOG("[%s] %s: saving fields every %d steps (about %d frames; %s)"
            % (motor, tid, every, plan["n_steps"] // every + 1, why))
        return {"save_every": every, "field_frames": plan["n_steps"] // every + 1}

    def running_motors(self):
        out = []
        for m in ("Rev0", "Rev1S", "Rev1D", "Rev2S"):
            stm = read_json(os.path.join(self.work, m, "state.json"), {})
            if stm and any(t.get("status") == "running" for t in stm.get("tasks", {}).values()):
                out.append(m)
        return out

    def lab_shared(self, profile):
        """Shared results folder of the v10 lab models: holds the static field-map reference(s) and the EQ
        calibration. The field map comes from the user's PC: ~/FIELDMAP_<M>_P20_fieldmap_results.json (or the same
        name in the work folder, or a <FIELDMAP>_results/fieldmap_results.json copied in full)."""
        shared = os.path.join(self.work, "shared_results")
        ref = "FIELDMAP_REV1S_P20" if "REV1S" in profile else "FIELDMAP_REV0_P20"
        dst_dir = os.path.join(shared, ref + "_results")
        dst = os.path.join(dst_dir, "fieldmap_results.json")
        if not os.path.isfile(dst):
            for cand in (os.path.join(os.path.expanduser("~"), ref + "_fieldmap_results.json"),
                         os.path.join(self.work, ref + "_fieldmap_results.json"),
                         os.path.join(os.path.expanduser("~"), ref + "_results", "fieldmap_results.json"),
                         os.path.join(os.path.expanduser("~"), "fieldmap_results.json")):
                if os.path.isfile(cand):
                    if not os.path.isdir(dst_dir):
                        os.makedirs(dst_dir)
                    shutil.copyfile(cand, dst)
                    LOG("[%s] field-map reference %s copied from %s" % (profile, ref, cand))
                    break
        if not os.path.isfile(dst):
            LOG("[%s] field-map reference %s not found (upload it as ~/%s_fieldmap_results.json) - the run goes "
                "ahead but its validation against the static field map is skipped" % (profile, ref, ref), "WARN")
        return shared

    def after_ok(self, motor, st, tid, kind, res, rec):
        if kind == "lab":
            src = res.get("results_dir")
            dst = os.path.join(self.work, "RESULTS_" + motor)
            n = 0
            if src and os.path.isdir(src):
                for root, dirs, files in os.walk(src):
                    dirs[:] = [x for x in dirs if x != "checkpoints"]
                    out = os.path.join(dst, os.path.relpath(root, src))
                    if not os.path.isdir(out):
                        os.makedirs(out)
                    for fn in files:
                        fp = os.path.join(root, fn)
                        if os.path.getsize(fp) <= 30 * 2 ** 20:
                            shutil.copy2(fp, os.path.join(out, fn))
                            n += 1
            LOG("[%s] finished: %d result files in %s\n%s" % (motor, n, dst, res.get("summary") or ""))
            return
        T = st["tasks"]
        gates = st.setdefault("gates", {})
        ipk = float(self.a.ipk)
        if kind == "tequiv":
            ref = T["solve_00"]["result"]["torques_Nm"]
            new = res["torques_Nm"]
            d_cu = 100.0 * abs(new["Torque_Cu"] / ref["Torque_Cu"] - 1)
            d_rot = 100.0 * abs(new["Torque_Rotor"] / ref["Torque_Rotor"] - 1)
            v = "PASS" if d_cu <= EQUIV_TOL_PCT else ("MARGINAL" if d_cu <= EQUIV_MAX_PCT else "FAIL")
            gates["equiv"] = {"verdict": v, "dev_copper_pct": d_cu, "dev_rotor_pct": d_rot,
                              "T_cu_united_mNm": -1e3 * ref["Torque_Cu"], "T_cu_split_mNm": -1e3 * new["Torque_Cu"]}
            LOG("[%s] GATE split-shaft equivalence: copper torque %+.3f vs %+.3f mN.m (%.2f %%), rotor %.2f %% -> %s"
                % (motor, -1e3 * new["Torque_Cu"], -1e3 * ref["Torque_Cu"], d_cu, d_rot, v),
                "INFO" if v != "FAIL" else "ERROR")
        if kind == "tstep":
            k = int(tid[-1])
            ref = T["solve_00"]["result"]["torques_Nm"]["Torque_Cu"]
            d = res.get("data", {})
            t0 = (d.get("Torque_Cu.Torque") or [float("nan")])[0]
            dev = 100.0 * abs(t0 / ref - 1) if ref else float("nan")
            per_step = (res.get("solve_minutes") or 0) * 60.0 / max(1, res.get("steps", 3))
            g = {"mesh_level": k, "dev_pct": dev, "T_cu_t0_mNm": -1e3 * t0, "T_cu_static_mNm": -1e3 * ref,
                 "seconds_per_step": per_step, "peak_rss_GB": rec.get("peak_rss_GB"),
                 "moving_t0_mNm": [1e3 * (d.get(n) or [float("nan")])[0] for n in sorted(d) if n.startswith("Moving") and n.endswith("Torque")]}
            ok = dev == dev and dev <= TSTEP_TOL_PCT
            last = k == 2
            if ok or (last and dev == dev and dev <= TSTEP_MAX_PCT):
                g["verdict"] = "PASS" if ok else "PASS_MESH_LIMITED"
                plan = self.production_plan(motor, per_step)
                g["plan"] = plan
                if plan.get("fits"):
                    st["tr_plan"] = dict(plan, mesh_level=k)
                    gates["tstep_summary"] = "%s at mesh MT%d (%.2f %%)" % (g["verdict"], k, dev)
                else:
                    g["verdict"] = "FAIL_HARD"
                    g["why"] = plan["why"]
                    gates["tstep_summary"] = plan["why"]
            else:
                g["verdict"] = "FAIL" if not last else "FAIL_HARD"
                g["why"] = "t=0 torque %.2f %% from the converged static torque" % dev
                gates["tstep_summary"] = g["why"] + (" after the finest mesh" if last else "")
            gates.setdefault("tstep", []).append(g)
            LOG("[%s] GATE short-step MT%d: copper torque at t=0 %.3f vs static %.3f mN.m (%.2f %%), %.0f s/step, "
                "peak %.1f GB -> %s%s" % (motor, k, -1e3 * t0, -1e3 * ref, dev, per_step, rec.get("peak_rss_GB") or 0,
                                         g["verdict"], (" | plan: %s" % g["plan"]["text"]) if g.get("plan") else ""),
                "INFO" if g["verdict"].startswith("PASS") else "WARN")

    def production_plan(self, motor, per_step):
        """Largest step count per electrical period whose predicted run fits one job (100 h limit), >= 45."""
        job = max(3600.0, getattr(self, "job_len", 100 * 3600.0)) - WALL_MARGIN_S - 2 * 3600
        target = self.a.tr_spp or TRANSIENT_SPP[motor]
        per = self.a.tr_periods or 1.25
        opts = [(x, per) for x in (target, 72, 60, 45) if x <= target] + ([(45, 1.0)] if per > 1.0 else [])
        for spp, periods in opts:
            n = int(math.ceil(spp * periods))
            pred = per_step * n * 1.15 + 1800
            if pred <= job:
                return {"fits": True, "spp": spp, "n_steps": n, "periods": periods, "predicted_s": pred,
                        "text": "%d steps/period x %.2f periods = %d steps, predicted %.1f h" % (spp, periods, n, pred / 3600)}
        n = 45
        return {"fits": False, "why": "does not fit one job: %.0f s/step -> %.1f h for one period at 45 steps "
                                      "(limit %.1f h). More cores or a coarser mesh needed." % (per_step, per_step * n / 3600, job / 3600)}

    # ------------------------------------------------------------------ one attempt of one task
    def run_attempt(self, motor, st, tid, kind, params, level):
        mdir = self.mdir(motor)
        t = st["tasks"].setdefault(tid, {"status": "pending", "attempts": 0, "history": []})
        t["attempts"] += 1
        n = t["attempts"]
        tdir = os.path.join(mdir, "tasks", "%s_try%02d" % (tid, n))
        shutil.rmtree(tdir, ignore_errors=True)
        os.makedirs(tdir)
        aedt_work = os.path.join(mdir, "aedt")
        if kind == "solve" or kind == "pilot":
            params = dict(params)
            params["level"] = LEVELS[level]
            params["psi_deg"] = float(self.refs.get("baseline", {}).get("psi_deg", -30.181))
            params["ipk"] = float(self.a.ipk)
            params["frozen"] = os.path.join(aedt_work, FROZEN_TAG[motor] + "_FINAL_HPC_FROZEN.aedt")
            params["keep_project"] = params.get("angle_index") == 0
            params["region_padding"] = self.a.padding
        if kind == "final":
            params = dict(params)
            params["region_padding"] = self.a.padding
        if kind == "tequiv":
            params = dict(params)
            params["level"] = LEVELS[params.get("level_index", level)]
            params["ipk"] = float(self.a.ipk)
            params["frozen"] = os.path.join(aedt_work, FROZEN_TAG[motor] + "_FINAL_HPC_FROZEN.aedt")
            params["keep_project"] = False
        inner_kind = {"pilot": "solve", "tequiv": "solve", "tstep": "trun", "tprod": "trun"}.get(kind, kind)
        task = {"kind": inner_kind, "task_id": tid, "params": params, "code_dir": self.code, "work_dir": aedt_work,
                "progress_file": os.path.join(tdir, "progress.txt"), "result_file": os.path.join(tdir, "result.json"),
                "stage_file": os.path.join(tdir, "stage.json"), "cores": self.cores,
                "ram_percent": int(100 * MEM_FRACTION) - 5}
        tpath = os.path.join(tdir, "task.json")
        atomic_json(tpath, task)
        t["status"] = "running"
        t["last_try"] = {"dir": tdir, "started": now(), "level": level, "job": self.job}
        self.save_state(motor, st)

        mode = st.get("launch_mode", "script")
        env = dict(self.aedt_env)
        env["HPCM_TASK"] = tpath
        aedt_log = os.path.join(tdir, "aedt.log")
        if mode == "pyaedt":
            env["HPCM_INNER_IMPORT"] = "1"
            ver = aedt_version_tag(self.aedt)
            m = re.search(r"v(\d{3})", self.aedt)
            if m:
                env["ANSYSEM_ROOT%s" % m.group(1)] = os.path.dirname(self.aedt)
            cmd = [sys.executable, os.path.join(self.work, "hpc_motor.py"), "--worker", tpath, "--aedt-version", ver or ""]
        elif mode == "script_alt":       # the exact form PyAEDT uses for -RunScriptAndExit
            cmd = [self.aedt, "-features=SF159726_SCRIPTOBJECT,SF6694_NON_GRAPHICAL_COMMAND_EXECUTION",
                   "-RunScriptAndExit", os.path.join(self.code, "inner.py")]
        else:
            cmd = [self.aedt, "-ng", "-waitforlicense",
                   "-features=SF159726_SCRIPTOBJECT,SF6694_NON_GRAPHICAL_COMMAND_EXECUTION",
                   "-Logfile", aedt_log, "-RunScriptAndExit", os.path.join(self.code, "inner.py")]
        LOG("[%s] %s attempt %d (%s%s): %s" % (motor, tid, n, mode,
                                              (", " + LEVELS[level]["name"]) if kind in ("solve", "pilot") else
                                              ((", mesh MT%s, %s steps" % (params.get("mesh_level"), params.get("n_steps")))
                                               if kind in ("tstep", "tprod") else ""),
                                              " ".join(shlex.quote(c) for c in cmd)))
        oom_before = oom_kills()
        t_start = time.time()
        if (motor != "smoke" and not self.a.allow_no_quota and os.path.abspath(self.work).startswith("/scratch")
                and scratch_quota() is None):
            LOG("[%s] %s: the account-wide /scratch quota cannot be read on this node ('myquota' / 'quota'), so "
                "the 50 GB limit cannot be protected - not starting it. Check SMOKE_RESULT.txt; rerun with "
                "--allow-no-quota only if the HPC team says that is fine" % (motor, tid), "ERROR")
            rec = {"try": n, "job": self.job, "level": level, "seconds": 0, "peak_rss_GB": 0, "exit": None,
                   "stage": None, "mode": mode, "dir": tdir, "outcome": "error", "kind": "disk",
                   "message": "account-wide scratch quota unreadable"}
            t["history"].append(rec)
            return rec, None
        if self.disk_left() < 2 * 2 ** 30:
            LOG("[%s] %s: less than 2 GB left of the %.1f GB disk budget - not starting it. Free space in %s "
                "(old *.aedtresults, tmp) or raise --disk-gb, then rerun with --retry-failed"
                % (motor, tid, self.a.disk_gb, self.work), "ERROR")
            rec = {"try": n, "job": self.job, "level": level, "seconds": 0, "peak_rss_GB": 0, "exit": None,
                   "stage": None, "mode": mode, "dir": tdir, "outcome": "error", "kind": "disk",
                   "message": "disk budget used up before the start"}
            t["history"].append(rec)
            return rec, None
        out = open(os.path.join(tdir, "stdout.txt"), "w")
        proc = subprocess.Popen(cmd, cwd=tdir, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        reason, peak, last_act, last_mt = None, 0, time.time(), 0.0
        prev_cpu = {}
        cpu_seen = {}
        watch = [tdir, aedt_work]
        samples = open(os.path.join(tdir, "resources.csv"), "w")
        samples.write("elapsed_s,rss_GB,cpu_s,processes\n")
        last_sample = 0.0
        last_cpu_s, peak_cores = 0.0, 0.0
        last_disk = time.time()
        hang_limit = HANG_S.get(inner_kind, 3600)
        while proc.poll() is None:
            time.sleep(POLL_S)
            pids, table = tree(proc.pid)
            rss = sum(_rss(p) for p in pids)
            cpu = sum(table[p]["cpu"] for p in pids if p in table)
            peak = max(peak, rss)
            disk_due = time.time() - last_disk >= DISK_CHECK_S
            if disk_due:
                last_disk = time.time()
            if time.time() - last_sample >= max(60, POLL_S):
                cpu_now = sum(cpu_seen.values()) / 100.0
                if last_sample:
                    peak_cores = max(peak_cores, (cpu_now - last_cpu_s) / max(1.0, time.time() - last_sample))
                last_cpu_s = cpu_now
                samples.write("%.0f,%.3f,%.0f,%d\n" % (time.time() - t_start, rss / 2.0 ** 30, cpu / 100.0, len(pids)))
                samples.flush()
                last_sample = time.time()
            for p in pids:
                if p in table:
                    cpu_seen[p] = max(cpu_seen.get(p, 0), table[p]["cpu"])
            busy = any(table[p]["cpu"] > prev_cpu.get(p, -1) for p in pids if p in table)
            prev_cpu = dict((p, table[p]["cpu"]) for p in pids if p in table)
            mt = newest_mtime(watch) if (not busy and time.time() - last_act > min(300, hang_limit / 4.0)) else last_mt
            if busy or mt > last_mt:
                last_act = time.time()
            last_mt = max(mt, last_mt)
            if rss > MEM_FRACTION * self.mem_limit:
                reason = "memory"
                LOG("[%s] %s: AEDT uses %.1f GB of %.1f GB - stopping it before SLURM kills the job"
                    % (motor, tid, rss / 2.0 ** 30, self.mem_limit / 2.0 ** 30), "WARN")
            elif time.time() - last_act > hang_limit:
                reason = "hang"
                LOG("[%s] %s: no CPU or file activity for %s - treating AEDT as frozen" % (motor, tid, hms(hang_limit)),
                    "WARN")
            elif disk_due and self.disk_left() < 0.5 * 2 ** 30:
                reason = "disk"
                LOG("[%s] %s: the %.0f GB disk budget is used up (work folder %.1f GB) - stopping AEDT before "
                    "the quota corrupts the project" % (motor, tid, self.a.disk_gb, self.disk_used() / 2.0 ** 30), "ERROR")
            elif self.deadline - time.time() < WALL_MARGIN_S:
                reason = "walltime"
                LOG("[%s] %s: %s of wall time left - stopping to resubmit" % (motor, tid,
                                                                            hms(self.deadline - time.time())), "WARN")
            if reason:
                kill_tree(proc.pid)
                break
        try:
            proc.wait(timeout=60)
        except Exception:
            kill_tree(proc.pid)
        kill_tree(proc.pid, grace=5)          # stragglers (solver engines) of a normal exit as well
        out.close()
        samples.close()
        secs = time.time() - t_start
        res = read_json(task["result_file"])
        stage = (read_json(task["stage_file"]) or {}).get("stage")
        started = os.path.isfile(task["progress_file"])
        cores_used = (sum(cpu_seen.values()) / 100.0) / max(1.0, secs)
        rec_cpu = {"avg_cores_busy": round(cores_used, 1), "cores_allocated": self.cores,
                   "peak_cores_busy_1min": round(peak_cores, 1)}
        rec = {"try": n, "job": self.job, "level": level, "seconds": round(secs), "peak_rss_GB": round(peak / 2.0 ** 30, 2),
               "exit": proc.returncode, "stage": stage, "mode": mode, "dir": tdir}
        if res and res.get("status") == "ok" and not reason:
            rec["outcome"] = "ok"
        elif reason == "walltime":
            rec["outcome"] = "walltime"
        else:
            rec["outcome"] = "error"
            if res and res.get("status") == "error" and not reason:
                rec["kind"] = res.get("error_kind", "python_error")
                rec["message"] = (res.get("message") or "")[:600]
            elif reason == "memory":
                rec["kind"] = "solve_oom" if stage in ("solving", "post") else "oom"
            elif reason == "disk":
                rec["kind"] = "disk"
                rec["message"] = "disk budget (--disk-gb %.0f) used up while running" % self.a.disk_gb
            elif reason == "hang":
                rec["kind"] = "hang"
                if not started:
                    txt = ""
                    for p in (aedt_log, os.path.join(tdir, "stdout.txt")):
                        try:
                            txt += open(p, errors="replace").read()[-20000:].lower()
                        except Exception:
                            pass
                    rec["kind"] = "license" if "licens" in txt else "launch"
            else:
                o2 = oom_kills()
                logtxt = ""
                for p in (aedt_log, os.path.join(tdir, "stdout.txt")):
                    try:
                        logtxt += open(p, errors="replace").read()[-20000:].lower()
                    except Exception:
                        pass
                if oom_before is not None and o2 is not None and o2 > oom_before:
                    rec["kind"] = "solve_oom" if stage in ("solving", "post") else "oom"
                elif "licens" in logtxt and ("fail" in logtxt or "unable" in logtxt or "not available" in logtxt
                                             or "denied" in logtxt or "checkout" in logtxt):
                    rec["kind"] = "license"
                elif not started:
                    rec["kind"] = "launch"
                else:
                    rec["kind"] = "crash"
                rec["message"] = "AEDT exited with code %s at stage %s" % (proc.returncode, stage)
        if kind == "tstep":
            try:
                rec["project_GB"] = self.clean_tstep(motor, int(params.get("mesh_level", 0))) / 2.0 ** 30
            except Exception as e:
                LOG("[%s] could not clean the short-step project (%s)" % (motor, e), "WARN")
        rec.update(rec_cpu)
        t["history"].append(rec)
        t["seconds_total"] = t.get("seconds_total", 0) + secs
        if secs > 120:
            LOG("[%s] %s CPU use: %.1f of %d allocated cores busy on average, %.1f at the busiest minute%s"
                % (motor, tid, cores_used, self.cores, peak_cores,
                   " - Maxwell is NOT using the allocation well; check the HPC settings in aedt.log" if
                   peak_cores < 0.4 * self.cores else ""),
                "INFO" if peak_cores >= 0.4 * self.cores else "WARN")
        LOG("[%s] %s attempt %d -> %s%s after %s, peak memory %.1f GB%s"
            % (motor, tid, n, rec["outcome"], (" (%s)" % rec["kind"]) if rec.get("kind") else "", hms(secs),
               peak / 2.0 ** 30, (": " + rec["message"]) if rec.get("message") else ""),
            "INFO" if rec["outcome"] == "ok" else "WARN")
        return rec, res

    # ------------------------------------------------------------------ a whole motor
    def time_ok(self, st, kind, est_override=None):
        """Enough wall time left to start this task? Unknown durations only force a new job when this one is
        already half used; a task longer than a whole job runs anyway (builds resume from checkpoints)."""
        left = self.deadline - time.time() - WALL_MARGIN_S
        if left == float("inf"):
            return True
        hist = st.get("durations", {}).get(kind)
        job_len = max(1.0, self.deadline - self.started)
        if est_override:
            return left > min(est_override, 0.95 * job_len - 60)
        if not hist:
            return left > min(EST_S.get(kind, 3600), 0.5 * job_len)
        est = max(hist) * 1.2
        if est > 0.95 * job_len:
            return left > 0.95 * job_len - 60
        return left > est

    def run_motor(self, motor, mode):
        st = self.load_state(motor)
        if self.job not in st["jobs"]:
            st["jobs"].append(self.job)
        st["mode"] = mode
        st["angles"] = self.a.angles
        tasks = self.plan(motor, mode)
        self.save_state(motor, st)
        for tid, params in tasks:
            kind = task_kind(tid)
            t = st["tasks"].setdefault(tid, {"status": "pending", "attempts": 0, "history": []})
            if t["status"] in ("done", "skipped"):
                continue
            if t["status"] != "failed" or self.a.retry_failed:
                params, why = self.prepare(motor, st, tid, kind, params)
                if why:
                    t["status"] = "skipped" if why.startswith("SKIP") else "failed"
                    t["why"] = why
                    self.save_state(motor, st)
                    LOG("[%s] %s %s: %s" % (motor, tid, t["status"], why), "INFO" if t["status"] == "skipped" else "WARN")
                    continue
            if t["status"] == "failed" and not self.a.retry_failed:
                LOG("[%s] %s failed earlier (%s) - skipped (use --retry-failed to try again)"
                    % (motor, tid, t.get("why", "?")), "WARN")
                if kind in FATAL_KINDS:
                    return "failed"
                continue
            if t["status"] == "failed":
                t.update({"status": "pending", "attempts": 0})
            level = PILOT_LEVEL if kind == "pilot" else (params.get("level_index", 0) if kind == "tequiv" else
                                                         max(st.get("level_floor", 0), t.get("level", 0),
                                                             self.a.start_level if kind == "solve" else 0))
            same_fail = 0
            while True:
                if not self.time_ok(st, "solve" if kind == "pilot" else kind,
                                    (st.get("tr_plan") or {}).get("predicted_s") if kind == "tprod" else
                                    (EST_LAB_S if kind == "lab" else None)):
                    return self.resubmit(motor, mode, st, "not enough wall time left for %s" % tid)
                rec, res = self.run_attempt(motor, st, tid, kind, params, level)
                if rec["outcome"] == "ok":
                    t["status"] = "done"
                    t["result"] = res
                    t["level"] = level
                    st.setdefault("durations", {}).setdefault("solve" if kind == "pilot" else kind, []).append(rec["seconds"])
                    if kind == "solve":
                        st["level_floor"] = max(st.get("level_floor", 0), level)
                    if tid == "probe":
                        st["probe"] = res.get("info")
                    st["launch_failures"] = 0
                    try:
                        self.after_ok(motor, st, tid, kind, res, rec)
                    except Exception as e:
                        LOG("[%s] gate evaluation for %s failed (%s)" % (motor, tid, e), "ERROR")
                    self.save_state(motor, st)
                    if kind in ("solve", "pilot"):
                        self.report()
                    break
                if rec["outcome"] == "walltime":
                    t["status"] = "pending"
                    t["walltime_kills"] = t.get("walltime_kills", 0) + 1
                    if kind == "tprod" and st.get("tr_plan"):
                        pl = st["tr_plan"]
                        lower = [x for x in (72, 60, 45) if x < pl["spp"]]
                        if lower:
                            pl.update({"spp": lower[0], "n_steps": int(math.ceil(lower[0] * pl["periods"]))})
                            LOG("[%s] %s: hit the wall-time limit - next job uses %d steps/period" % (motor, tid, lower[0]), "WARN")
                    if kind in ("solve", "pilot") and t["walltime_kills"] >= 2 and level + 1 < len(LEVELS):
                        level += 1
                        LOG("[%s] %s: stopped by the wall-time limit twice - next job uses %s"
                            % (motor, tid, LEVELS[level]["name"]), "WARN")
                    t["level"] = level
                    self.save_state(motor, st)
                    return self.resubmit(motor, mode, st, "wall-time limit")
                k = rec["kind"]
                if k == "launch":
                    st["launch_failures"] = st.get("launch_failures", 0) + 1
                    if st["launch_failures"] >= 2:
                        cur = st.get("launch_mode", "script")
                        nxt = {"script": "script_alt", "script_alt": "pyaedt"}.get(cur)
                        if nxt == "pyaedt" and not self.ensure_pyaedt():
                            nxt = None
                        if nxt:
                            st["launch_mode"] = nxt
                            st["launch_failures"] = 0
                            same_fail = 0
                            LOG("[%s] AEDT did not run the task script twice in '%s' mode - switching to '%s'"
                                % (motor, cur, nxt), "WARN")
                same_fail += 1
                real = t["attempts"] - t.get("walltime_kills", 0)
                verdict, new_level = decide(kind, k, same_fail, level, real)
                if verdict == "retry" and new_level != level:
                    level, same_fail = new_level, 0
                    LOG("[%s] %s: stepping down the solver ladder to %s" % (motor, tid, LEVELS[level]["name"]), "WARN")
                if verdict == "fail":
                    if kind == "solve" and k in ("oom", "solve_oom", "hang", "crash"):
                        st["level_floor"] = max(st.get("level_floor", 0), level)   # later angles skip doomed levels
                    t["status"] = "failed"
                    t["why"] = "%s: %s" % (k, rec.get("message", ""))
                    self.save_state(motor, st)
                    fatal = kind in FATAL_KINDS
                    if kind == "tprod":
                        self.salvage(motor, st, tid, params)
                    if kind == "tstep":
                        st.setdefault("gates", {}).setdefault("tstep", []).append(
                            {"mesh_level": params.get("mesh_level"), "verdict": "FAIL_HARD", "why": t["why"][:200]})
                        st["gates"]["tstep_summary"] = "MT%s run failed: %s" % (params.get("mesh_level"), t["why"][:200])
                    LOG("[%s] %s FAILED for good after %d attempts (%s). %s"
                        % (motor, tid, t["attempts"], t["why"][:300],
                           "This motor cannot continue." if fatal else
                           ("Moving on to the next angle." if kind in ("solve", "pilot") else
                            "Stages that depend on it will not run.")), "ERROR")
                    self.report()
                    if fatal:
                        return "failed"
                    break
                t["level"] = level
                self.save_state(motor, st)
                if k in ("license", "launch", "lock"):
                    wait = BACKOFF_S[min(same_fail - 1, len(BACKOFF_S) - 1)]
                    LOG("[%s] %s: waiting %s before the next try (%s)" % (motor, tid, hms(wait), k))
                    if self.deadline - time.time() - WALL_MARGIN_S < wait + 600:
                        return self.resubmit(motor, mode, st, "back-off would cross the wall-time limit")
                    time.sleep(wait)
        self.report()
        return "done"

    def salvage(self, motor, st, tid, params):
        """A production run that died: re-open its project and export every time step that was solved."""
        p = dict(params)
        p["salvage"] = True
        sid = tid + "_salvage"
        rec, res = self.run_attempt(motor, st, sid, "tprod", p, 0)
        t = st["tasks"][sid]
        if rec["outcome"] == "ok":
            t["status"] = "done"
            t["result"] = res
            n = len((res.get("data") or {}).get("time_s") or [])
            LOG("[%s] %s: salvaged %d solved time steps (partial waveform kept in the report)" % (motor, tid, n), "WARN")
        else:
            t["status"] = "failed"
            t["why"] = rec.get("message", "")
        self.save_state(motor, st)

    # ------------------------------------------------------------------ resubmission / fan-out
    def sbatch(self, motor, mode, extra=None, dependency=True):
        script = os.path.join(self.work, "hpc_motor.py")
        cmd = ["sbatch", "--parsable", "--job-name", "pcbm_%s" % motor,
               "--output", os.path.join(self.work, "pcbmotor_%s_%%j.out" % motor)]
        if dependency and os.environ.get("SLURM_JOB_ID"):
            cmd += ["--dependency", "afterany:%s" % os.environ["SLURM_JOB_ID"]]
        for k, env in (("--ntasks", "SLURM_NTASKS"), ("--mem-per-cpu", "SLURM_MEM_PER_CPU"),
                       ("--partition", "SLURM_JOB_PARTITION"), ("--account", "SLURM_JOB_ACCOUNT")):
            if os.environ.get(env) and not (extra and k in extra):
                cmd += [k, os.environ[env]]
        if extra:
            for k, v in extra.items():
                cmd += [k, str(v)]
        cmd += [script, "--motor", motor, "--mode", mode, "--work", self.work, "--angles", str(self.a.angles),
                "--ipk", str(self.a.ipk), "--padding", str(self.a.padding), "--rpm", str(self.a.rpm),
                "--rev1-ntasks", str(self.a.rev1_ntasks), "--start-level", str(self.a.start_level),
                "--tr-runs", self.a.tr_runs, "--disk-gb", str(self.a.disk_gb)] + \
              (["--max-resubmits", str(self.a.max_resubmits)] if self.a.max_resubmits is not None else []) + \
              (["--allow-no-quota"] if self.a.allow_no_quota else []) + (["--tr-spp", str(self.a.tr_spp)] if self.a.tr_spp else []) + \
              (["--tr-periods", str(self.a.tr_periods)] if self.a.tr_periods else []) + ["--no-fanout", "--resized"]
        rc, out = sh(cmd, timeout=120)
        jid = out.strip().split(";")[0] if rc == 0 else None
        return jid, cmd, out

    def resubmit(self, motor, mode, st, why):
        st["resubmits"] = st.get("resubmits", 0) + 1
        self.save_state(motor, st)
        limit = self.a.max_resubmits if getattr(self.a, "max_resubmits", None) is not None else MAX_RESUBMITS
        if st["resubmits"] > limit:
            txt = "sbatch %s --motor %s --mode %s --work %s" % (os.path.join(self.work, "hpc_motor.py"), motor, mode, self.work)
            with open(os.path.join(self.work, "RESUBMIT_ME.txt"), "a") as f:
                f.write("%s  %s: %s\n%s\n\n" % (now(), motor, why, txt))
            LOG("[%s] %s. Automatic resubmission is limited to %d per motor (--max-resubmits) - NOT resubmitting. "
                "The checkpoint is saved; to continue, review supervisor.log and run:\n    %s"
                % (motor, why, limit, txt), "WARN")
            return "stopped"
        jid, cmd, out = self.sbatch(motor, mode)
        if jid:
            LOG("[%s] %s: continuing in job %s (starts when this one ends)" % (motor, why, jid))
            st["next_job"] = jid
            self.save_state(motor, st)
            return "resubmitted"
        txt = " ".join(shlex.quote(c) for c in cmd)
        LOG("[%s] %s, and sbatch from this node failed (%s). Run this on the login node to continue:\n    %s"
            % (motor, why, out.strip()[:300], txt), "ERROR")
        with open(os.path.join(self.work, "RESUBMIT_ME.txt"), "a") as f:
            f.write("%s  %s\n%s\n\n" % (now(), motor, txt))
        return "resubmit_failed"

    def ensure_pyaedt(self):
        rc, _ = sh([sys.executable, "-c", "import ansys.aedt.core"], timeout=120)
        if rc == 0:
            return True
        if not getattr(self.a, "allow_pip", False):
            LOG("PyAEDT is not installed. The UCT HPC asks users to check with the admins before installing libraries, "
                "so it is not installed automatically. Ask hpc@uct.ac.za, then rerun with --allow-pip", "WARN")
            return False
        LOG("PyAEDT not installed - trying pip install --user pyaedt (allowed with --allow-pip)")
        rc, out = sh([sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyaedt"], timeout=1200)
        if rc == 0:
            rc, _ = sh([sys.executable, "-c", "import ansys.aedt.core"], timeout=120)
        if rc != 0:
            LOG("PyAEDT could not be installed (no internet on this node?): %s" % out.strip()[-300:], "WARN")
        return rc == 0

    # ------------------------------------------------------------------ reporting
    def report(self):
        try:
            build_reports(self.work, self.refs, self.a.ipk)
        except Exception as e:
            LOG("Report generation failed (%s) - results are still in state.json" % e, "WARN")


# ============================================================================================ reports
def _get(d, *keys):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def analyse_motor(st, refs, ipk):
    """Turn the solved angles of one motor into K, ripple and the comparisons."""
    motor = st["motor"]
    rows, pilot = [], None
    for tid, t in sorted(st.get("tasks", {}).items()):
        if not (tid.startswith("solve_") or tid.startswith("pilot_")):
            continue
        r = t.get("result") if t.get("status") == "done" else None
        row = {"task": tid, "status": t.get("status"), "attempts": t.get("attempts"), "why": t.get("why")}
        if r:
            tq = r["torques_Nm"]
            chk = r.get("checks", {})
            dev = chk.get("rotor_vs_copper_pct")
            row.update({"theta_deg": r["theta_deg"], "T_cu_mNm": -1e3 * tq["Torque_Cu"], "T_rotor_mNm": 1e3 * tq["Torque_Rotor"],
                        "rotor_vs_copper_pct": dev, "level": _get(r, "level", "name"), "solve_min": r.get("solve_minutes"),
                        "boards": dict((k[len("Torque_"):], -1e3 * v) for k, v in tq.items() if "_PCB" in k),
                        "stators": dict((k[len("Torque_"):], -1e3 * v) for k, v in tq.items()
                                        if k.startswith("Torque_S") and "_PCB" not in k),
                        "quality": "REJECT" if (dev is None or dev > 10) else ("WARN" if dev > 3 else "OK"),
                        "peak_rss_GB": max([h.get("peak_rss_GB", 0) for h in t.get("history", []) if h.get("outcome") == "ok"] or [0])})
            mesh = _get(r, "extras", "mesh_stats") or ""
            m = re.search(r"(?i)total[^\n]*?(\d[\d,]{3,})", mesh)
            if m:
                row["mesh_elements"] = int(m.group(1).replace(",", ""))
        if tid.startswith("pilot_"):
            pilot = row
        else:
            rows.append(row)
    ok = [r for r in rows if r.get("quality") in ("OK", "WARN")]
    out = {"motor": motor, "angles_planned": st.get("angles"), "angles_ok": len(ok), "rows": rows, "pilot": pilot}
    fm = _get(refs, motor, "fieldmap", "machine", "PHASE_A", "K1_mNm_per_A")
    det = _get(refs, motor, "detailed", "machine_phaseA_K1_mNm_per_A")
    out["ref_fieldmap"] = fm
    out["ref_detailed"] = det
    use = ok or ([pilot] if pilot and pilot.get("quality") in ("OK", "WARN") else [])
    if use:
        tcu = [r["T_cu_mNm"] for r in use]
        trot = [r["T_rotor_mNm"] for r in use]
        mean_cu = sum(tcu) / len(tcu)
        K = mean_cu / (1.5 * ipk)
        out["K_mNm_per_A"] = K
        out["K_from_rotor_mNm_per_A"] = (sum(trot) / len(trot)) / (1.5 * ipk)
        out["T_mean_mNm_at_Ipk"] = mean_cu
        out["ripple_pkpk_pct"] = 100.0 * (max(tcu) - min(tcu)) / abs(mean_cu) if len(tcu) > 1 and mean_cu else None
        out["E1_peak_V_at_1000rpm"] = K * 1e-3 * 1000.0 * 2 * math.pi / 60.0
        out["E1_rms_V_at_1000rpm"] = out["E1_peak_V_at_1000rpm"] / math.sqrt(2)
        planned = st.get("angles") or len(use)
        out["basis"] = (("mean of %d angles over one ripple period" % len(use)) if len(use) >= planned else
                        ("mean of %d of %d angles - not a full ripple period, may carry part of the ripple" % (len(use), planned))) \
            if ok else "pilot angle only (single angle - includes ripple)"
        out["complete"] = bool(ok) and len(ok) == st.get("angles")
        if fm:
            out["vs_fieldmap_pct"] = 100.0 * (K / fm - 1)
        if det:
            out["vs_detailed_pct"] = 100.0 * (K / det - 1)
        if fm and det:
            lo, hi = min(fm, det), max(fm, det)
            out["bracket"] = "INSIDE" if lo * 0.98 <= K <= hi * 1.02 else ("BELOW" if K < lo else "ABOVE")
        boards = {}
        for name in sorted(use[0].get("boards", {})):
            vals = [r["boards"].get(name) for r in use if r.get("boards", {}).get(name) is not None]
            if not vals:
                continue
            kb = (sum(vals) / len(vals)) / (1.5 * ipk)
            key = name.replace("_PCB", "_B")
            b = {"K_mNm_per_A": kb}
            f = _get(refs, motor, "fieldmap", "boards", key + "_PHASE_A", "K1_mNm_per_A")
            d = _get(refs, motor, "detailed", "boards", key, "K1_mNm_per_A")
            if f:
                b["fieldmap"] = f
                b["vs_fieldmap_pct"] = 100.0 * (kb / f - 1)
            if d:
                b["detailed"] = d
                b["vs_detailed_pct"] = 100.0 * (kb / d - 1)
            boards[key] = b
        out["boards"] = boards
        sts = {}
        for s in ("S1", "S2", "S3"):
            vals = [r["stators"].get(s) for r in use if r.get("stators", {}).get(s) is not None]
            if vals:
                sts[s] = (sum(vals) / len(vals)) / (1.5 * ipk)
        if not sts and boards:
            sts["S1"] = sum(b["K_mNm_per_A"] for b in boards.values())
        out["stators"] = sts
    return out


def _dft(y, hmax=13):
    N = len(y)
    out = {}
    for h in range(0, hmax + 1):
        re_ = sum(y[k] * math.cos(2 * math.pi * h * k / N) for k in range(N))
        im_ = sum(y[k] * math.sin(2 * math.pi * h * k / N) for k in range(N))
        amp = (re_ / N) if h == 0 else 2.0 * math.hypot(re_, im_) / N
        out[h] = (amp, math.degrees(math.atan2(-im_, re_)))
    return out


def _read_fld_rows(path):
    rows = []
    try:
        for line in open(path):
            parts = line.replace(",", " ").split()
            if len(parts) >= 6:
                try:
                    rows.append([float(v) for v in parts[:6]])
                except ValueError:
                    pass
    except Exception:
        pass
    return rows


def analyse_transient(st, ipk, K_static, refs):
    """Waveform metrics over the LAST full electrical period of each production run."""
    motor = st["motor"]
    T = st.get("tasks", {})
    n_st = {"Rev0": 1, "Rev1S": 2, "Rev1D": 2, "Rev2S": 3}[motor]
    out = {"gates": st.get("gates", {}), "plan": st.get("tr_plan")}
    for run in ("tprod_noload", "tprod_load"):
        t = T.get(run, {})
        r = t.get("result") if t.get("status") == "done" else None
        partial = False
        if not r and (T.get(run + "_salvage", {}).get("status") == "done"):
            r, partial = T[run + "_salvage"]["result"], True
        if not r:
            out[run] = {"status": t.get("status"), "why": t.get("why")}
            continue
        d = r.get("data") or {}
        spp = int(r.get("steps_per_period") or 0)
        tt = d.get("time_s") or []
        a = {"status": "partial" if partial else "done", "steps_solved": len(tt), "steps_per_period": spp,
             "mesh": r.get("mesh"), "solve_min": r.get("solve_minutes"), "rpm": r.get("rpm"),
             "field_dir": r.get("field_dir"), "field_files": len(r.get("fields") or [])}
        if not spp or len(tt) < spp + 1:
            a["note"] = "fewer than one electrical period solved - no waveform metrics"
            out[run] = a
            continue
        last = lambda key: (d.get(key) or [])[-spp:]
        wm = 2 * math.pi * float(r.get("rpm") or 1000.0) / 60.0
        we = wm * 8
        moving = [k for k in d if k.startswith("Moving") and k.endswith("Torque")]
        tq = [sum(vals) for vals in zip(*[last(k) for k in moving])] if moving else []
        cu = [-x for x in last("Torque_Cu.Torque")] if d.get("Torque_Cu.Torque") else []
        if tq:
            m = sum(tq) / len(tq)
            a["torque_mean_mNm"] = 1e3 * m
            a["torque_pkpk_mNm"] = 1e3 * (max(tq) - min(tq))
            a["torque_ripple_pct"] = 100.0 * (max(tq) - min(tq)) / abs(m) if abs(m) > 1e-9 else None
        if cu:
            a["torque_copper_mean_mNm"] = 1e3 * sum(cu) / len(cu)
        emf = {}
        for ph in ("A", "B", "C"):
            y = last("InducedVoltage(Phase%s)" % ph)
            if len(y) == spp:
                h = _dft(y)
                e1 = h[1][0]
                emf[ph] = {"E1_peak_V": e1, "E1_rms_V": e1 / math.sqrt(2), "phase_deg": h[1][1],
                           "harmonics_pct": dict((n, 100.0 * h[n][0] / e1 if e1 else None) for n in (3, 5, 7, 9, 11, 13)),
                           "THD_pct": 100.0 * math.sqrt(sum(h[n][0] ** 2 for n in range(2, 14))) / e1 if e1 else None}
            lam = last("FluxLinkage(Phase%s)" % ph)
            if len(lam) == spp and ph in emf:
                emf[ph]["lambda1_peak_mWb"] = 1e3 * _dft(lam)[1][0]
                emf[ph]["E1_over_we_lambda1"] = emf[ph]["E1_peak_V"] / (we * _dft(lam)[1][0]) if _dft(lam)[1][0] else None
        if emf:
            amps = [v["E1_peak_V"] for v in emf.values()]
            a["emf"] = emf
            a["emf_balance_pct"] = 100.0 * (max(amps) - min(amps)) / (sum(amps) / len(amps))
            if len(emf) == 3:
                pa, pb, pc = emf["A"]["phase_deg"], emf["B"]["phase_deg"], emf["C"]["phase_deg"]
                a["emf_phase_steps_deg"] = [((pb - pa + 180) % 360) - 180, ((pc - pb + 180) % 360) - 180]
            if K_static:
                a["E1_predicted_from_static_K_V"] = K_static * 1e-3 * wm
        loss = last("SolidLoss")
        if loss:
            a["solid_loss_mean_W"] = sum(loss) / len(loss)
        cur = last("Current(PhaseA)")
        if cur:
            a["current_A_peak_V"] = _dft(cur)[1][0]
        # steel |B| over the saved frames
        fd = r.get("field_dir")
        if fd and os.path.isdir(fd):
            steel = {}
            for fn in sorted(os.listdir(fd)):
                if fn.startswith("Bsteel_") and fn.endswith(".fld"):
                    part = fn[len("Bsteel_"):].split("_t")[0]
                    rows = _read_fld_rows(os.path.join(fd, fn))
                    if rows:
                        mx = max(math.sqrt(x[3] ** 2 + x[4] ** 2 + x[5] ** 2) for x in rows)
                        steel[part] = max(steel.get(part, 0.0), mx)
            if steel:
                a["steel_Bmax_T"] = steel
        out[run] = a
    nl, ld = out.get("tprod_noload", {}), out.get("tprod_load", {})
    if ld.get("torque_mean_mNm") is not None and ipk:
        Kd = ld["torque_mean_mNm"] / (1.5 * ipk)
        ld["K_dynamic_mNm_per_A"] = Kd
        if K_static:
            ld["K_dynamic_vs_static_pct"] = 100.0 * (Kd / K_static - 1)
        r_ph = n_st * 5 * R_BOARD_PHASE
        ld["P_dc_estimate_W"] = 1.5 * ipk ** 2 * r_ph
        if ld.get("solid_loss_mean_W") is not None:
            p_mech = 1e-3 * ld["torque_mean_mNm"] * 2 * math.pi * float(ld.get("rpm") or 1000) / 60.0
            ld["P_mech_W"] = p_mech
            ld["eta_EM_pct"] = 100.0 * p_mech / (p_mech + ld["solid_loss_mean_W"]) if p_mech > 0 else None
            if nl.get("solid_loss_mean_W") is not None:
                ld["loss_excess_over_dc_and_noload_W"] = ld["solid_loss_mean_W"] - ld["P_dc_estimate_W"] - nl["solid_loss_mean_W"]
    if nl.get("torque_pkpk_mNm") is not None:
        nl["cogging_pkpk_mNm"] = nl["torque_pkpk_mNm"]
    return out


def transient_text(motor, tr):
    L = []
    g = tr.get("gates", {})
    if g.get("equiv"):
        e = g["equiv"]
        L.append("  split-shaft equivalence (static, 0 deg): %.3f vs %.3f mN.m united -> %.2f %% (rotor %.2f %%): %s"
                 % (e["T_cu_split_mNm"], e["T_cu_united_mNm"], e["dev_copper_pct"], e["dev_rotor_pct"], e["verdict"]))
    for s_ in g.get("tstep", []):
        if "dev_pct" in s_:
            L.append("  short-step MT%s: t=0 copper torque %.3f vs static %.3f mN.m (%.2f %%), %.0f s/step, %.1f GB: %s"
                     % (s_["mesh_level"], s_["T_cu_t0_mNm"], s_["T_cu_static_mNm"], s_["dev_pct"], s_["seconds_per_step"],
                        s_.get("peak_rss_GB") or 0, s_["verdict"]))
        else:
            L.append("  short-step MT%s: %s (%s)" % (s_.get("mesh_level"), s_.get("verdict"), s_.get("why")))
    if tr.get("plan"):
        L.append("  production plan: %s, mesh MT%s" % (tr["plan"].get("text"), tr["plan"].get("mesh_level")))
    for run, label in (("tprod_noload", "no load"), ("tprod_load", "loaded")):
        a = tr.get(run, {})
        if a.get("status") not in ("done", "partial"):
            L.append("  %s run: %s %s" % (label, a.get("status") or "not run", ("- " + a["why"]) if a.get("why") else ""))
            continue
        L.append("  %s run (%s, %s steps/period, %s steps, %s min):" % (label, a["status"], a.get("steps_per_period"),
                                                                       a.get("steps_solved"), a.get("solve_min")))
        if a.get("note"):
            L.append("    " + a["note"])
        if a.get("emf"):
            for ph, e in sorted(a["emf"].items()):
                L.append("    back-EMF %s: %.4f V peak / %.4f V rms, THD %.2f %%, h3 %.2f h5 %.2f h7 %.2f %%%s"
                         % (ph, e["E1_peak_V"], e["E1_rms_V"], e["THD_pct"] or 0, e["harmonics_pct"][3] or 0,
                            e["harmonics_pct"][5] or 0, e["harmonics_pct"][7] or 0,
                            (", E1/(we*lambda1) %.3f" % e["E1_over_we_lambda1"]) if e.get("E1_over_we_lambda1") else ""))
            L.append("    phase balance %.2f %%, phase steps %s deg%s" % (
                a.get("emf_balance_pct") or 0, ["%.1f" % x for x in a.get("emf_phase_steps_deg", [])],
                (", static K predicts E1 = %.4f V" % a["E1_predicted_from_static_K_V"]) if a.get("E1_predicted_from_static_K_V") else ""))
        if a.get("cogging_pkpk_mNm") is not None:
            L.append("    cogging torque: %.4f mN.m peak-to-peak (mean %.4f)" % (a["cogging_pkpk_mNm"], a.get("torque_mean_mNm") or 0))
        if run == "tprod_load" and a.get("torque_mean_mNm") is not None:
            L.append("    torque %.3f mN.m mean (copper %.3f), ripple %.2f %% -> K_dyn %.3f mN.m/A (%s vs static)"
                     % (a["torque_mean_mNm"], a.get("torque_copper_mean_mNm") or float("nan"), a.get("torque_ripple_pct") or 0,
                        a.get("K_dynamic_mNm_per_A") or float("nan"), fmt(a.get("K_dynamic_vs_static_pct"), "%+.2f%%")))
        if a.get("solid_loss_mean_W") is not None:
            L.append("    solid losses (copper + magnets, eddy incl.) %.5f W%s" % (a["solid_loss_mean_W"],
                     (" | DC estimate %.5f W, excess %.5f W, P_mech %.4f W, EM efficiency %.1f %% (no bearing/windage)"
                      % (a["P_dc_estimate_W"], a.get("loss_excess_over_dc_and_noload_W") or float("nan"), a["P_mech_W"],
                         a.get("eta_EM_pct") or float("nan"))) if run == "tprod_load" and a.get("P_mech_W") is not None else ""))
        if a.get("steel_Bmax_T"):
            L.append("    steel |B|max over saved frames: %s" % ", ".join("%s %.2f T%s" % (k, v, " (above 1.6 T)" if v > 1.6 else "")
                                                                     for k, v in sorted(a["steel_Bmax_T"].items())))
        if a.get("field_files"):
            L.append("    %d field files in %s (make_field_animation.py turns them into frames/GIF)" % (a["field_files"], a.get("field_dir")))
    return L


def fmt(x, f="%.3f"):
    return "-" if x is None else (f % x)


def build_reports(work, refs, ipk):
    allm = {}
    for motor in MOTORS:
        st = read_json(os.path.join(work, motor, "state.json"))
        if not st:
            continue
        a = analyse_motor(st, refs, ipk)
        sb = {}
        for tid, tk in st.get("tasks", {}).items():
            r = tk.get("result") or {}
            if tid.startswith("solve_") and tk.get("status") == "done":
                for part, v in (r.get("steel_B") or {}).items():
                    if v:
                        sb[part] = max(sb.get(part, 0.0), v.get("max_T", 0.0))
        if sb:
            a["steel_Bmax_static_T"] = sb
        if any(k.startswith(("tprep", "tstep", "tprod", "tequiv")) for k in st.get("tasks", {})):
            a["transient"] = analyse_transient(st, ipk, a.get("K_mNm_per_A"), refs)
        a["tasks"] = dict((k, {"status": v.get("status"), "attempts": v.get("attempts"), "why": v.get("why")})
                          for k, v in st.get("tasks", {}).items())
        allm[motor] = a
        rd = os.path.join(work, motor, "results")
        if not os.path.isdir(rd):
            os.makedirs(rd)
        atomic_json(os.path.join(rd, "%s_summary.json" % motor), a)
        with open(os.path.join(rd, "%s_angles.csv" % motor), "w") as f:
            f.write("task,status,theta_deg,T_copper_mNm,T_rotor_mNm,rotor_vs_copper_pct,quality,level,solve_min,peak_rss_GB,mesh_elements\n")
            for r in a["rows"] + ([a["pilot"]] if a.get("pilot") else []):
                f.write(",".join(str(r.get(k, "")) for k in ("task", "status", "theta_deg", "T_cu_mNm", "T_rotor_mNm",
                                                            "rotor_vs_copper_pct", "quality", "level", "solve_min",
                                                            "peak_rss_GB", "mesh_elements")) + "\n")
        if a.get("boards"):
            with open(os.path.join(rd, "%s_boards.csv" % motor), "w") as f:
                f.write("board,K_full_mNm_per_A,K_fieldmap,vs_fieldmap_pct,K_detailed,vs_detailed_pct\n")
                for b, v in sorted(a["boards"].items()):
                    f.write("%s,%s,%s,%s,%s,%s\n" % (b, fmt(v.get("K_mNm_per_A"), "%.4f"), fmt(v.get("fieldmap"), "%.4f"),
                                                     fmt(v.get("vs_fieldmap_pct"), "%.2f"), fmt(v.get("detailed"), "%.4f"),
                                                     fmt(v.get("vs_detailed_pct"), "%.2f")))
    L = ["PCB AXIAL-FLUX MOTOR - FULL-MOTOR MAXWELL SOLVES (hpc_motor %s)" % VERSION,
         "Updated %s. K = per-phase torque constant = mean 3-phase torque / (1.5 x Ipk), Ipk = %g A, synchronous"
         % (now(), ipk),
         "currents at the baseline current angle. Torque taken on the copper (Lorentz); rotor virtual work as a check.",
         "References: field map = FIELDMAP_*_P20; detailed = sum of single-board FEM runs (board-by-board).", ""]
    L.append("%-8s %-9s %10s %10s %9s %10s %9s %9s %8s %s" % ("motor", "angles", "K mNm/A", "field map", "vs FM",
                                                                "detailed", "vs det", "bracket", "ripple", "basis"))
    for motor in MOTORS:
        a = allm.get(motor)
        if not a:
            L.append("%-8s not started" % motor)
            continue
        L.append("%-8s %-9s %10s %10s %9s %10s %9s %9s %8s %s" % (
            motor, "%s/%s" % (a.get("angles_ok"), a.get("angles_planned") or "-"), fmt(a.get("K_mNm_per_A")),
            fmt(a.get("ref_fieldmap")), fmt(a.get("vs_fieldmap_pct"), "%+.2f%%"), fmt(a.get("ref_detailed")),
            fmt(a.get("vs_detailed_pct"), "%+.2f%%"), a.get("bracket", "-"), fmt(a.get("ripple_pkpk_pct"), "%.1f%%"),
            a.get("basis", "no solved angle yet")))
    for motor in MOTORS:
        a = allm.get(motor)
        if not a:
            continue
        L += ["", "--- %s ---" % MOTOR_TEXT[motor]]
        L.append("tasks: " + ", ".join("%s %s" % (k, v["status"]) for k, v in sorted(a["tasks"].items())))
        for k, v in sorted(a["tasks"].items()):
            if v.get("status") == "failed":
                L.append("  FAILED %s: %s" % (k, (v.get("why") or "")[:400]))
        if a.get("K_mNm_per_A") is not None:
            L.append("K = %.3f mN.m/A (copper), %.3f mN.m/A (rotor virtual work); back-EMF %.3f V peak / %.3f V rms per "
                     "phase at 1000 rpm" % (a["K_mNm_per_A"], a["K_from_rotor_mNm_per_A"], a["E1_peak_V_at_1000rpm"],
                                            a["E1_rms_V_at_1000rpm"]))
            if a.get("stators"):
                L.append("per stator: " + ", ".join("%s %.3f" % kv for kv in sorted(a["stators"].items())))
        for r in a["rows"] + ([a["pilot"]] if a.get("pilot") else []):
            if r.get("theta_deg") is None:
                L.append("  %-9s %s" % (r["task"], r.get("status")))
                continue
            L.append("  %-9s theta %6.3f deg  T_cu %8.3f mNm  T_rotor %8.3f mNm  dev %5.2f%%  %-6s %s, %s min, %s GB%s"
                     % (r["task"], r["theta_deg"], r["T_cu_mNm"], r["T_rotor_mNm"], r["rotor_vs_copper_pct"] or 0,
                        r["quality"], r.get("level"), r.get("solve_min"), r.get("peak_rss_GB"),
                        (", %d elements" % r["mesh_elements"]) if r.get("mesh_elements") else ""))
        if a.get("steel_Bmax_static_T"):
            L.append("  steel |B|max over the static angles: %s" % ", ".join(
                "%s %.2f T%s" % (k, v, " (above 1.6 T - check)" if v > 1.6 else "") for k, v in sorted(a["steel_Bmax_static_T"].items())))
        if a.get("transient"):
            L.append("  TRANSIENT (T-Omega, rotating band%s):" % ("s" if motor != "Rev0" else ""))
            L += transient_text(motor, a["transient"])
        if a.get("boards"):
            L.append("  board    K full   field map    vs FM   detailed   vs det")
            for b, v in sorted(a["boards"].items()):
                L.append("  %-6s %8.4f %10s %8s %10s %8s" % (b, v["K_mNm_per_A"], fmt(v.get("fieldmap"), "%.4f"),
                                                          fmt(v.get("vs_fieldmap_pct"), "%+.2f%%"),
                                                          fmt(v.get("detailed"), "%.4f"), fmt(v.get("vs_detailed_pct"), "%+.2f%%")))
    L += ["", "Quality: OK = rotor and copper torque agree within 3 %; WARN = 3-10 % (kept, check mesh); REJECT = over 10 %"
          " or missing (excluded from K).", "bracket: INSIDE = K lies between the field map and the detailed sum (2 % "
          "tolerance). The field map exceeds the detailed sum by ~5 %; this solve decides where the truth lies."]
    with open(os.path.join(work, "RESULTS.txt"), "w") as f:
        f.write("\n".join(L) + "\n")
    try:
        with open(os.path.join(work, "make_field_animation.py"), "w") as f:
            f.write(ANIMATION_HELPER)
    except Exception:
        pass
    atomic_json(os.path.join(work, "RESULTS.json"), allm)
    return "\n".join(L)


# ============================================================================================ entry points
def default_work():
    if os.environ.get("HPCM_WORK"):
        return os.environ["HPCM_WORK"]
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "user"
    s = os.path.join("/scratch", user)
    if os.path.isdir(s) and os.access(s, os.W_OK):
        return os.path.join(s, "pcbmotor_hpc")
    return os.path.join(os.path.expanduser("~"), "pcbmotor_hpc")


def self_path():
    p = os.path.abspath(sys.argv[0])
    return p if os.path.isfile(p) else os.path.abspath(__file__)


def install_self(work):
    """Keep a copy of this exact file in the work folder (resubmitted jobs run it)."""
    dst = os.path.join(work, "hpc_motor.py")
    src = self_path()
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst + ".tmp")
        os.chmod(dst + ".tmp", 0o755)
        os.replace(dst + ".tmp", dst)
    return dst


def worker_main(task_path, version):
    """PyAEDT launcher (fallback when ansysedt -RunScriptAndExit does not run the inner script)."""
    d = read_json(task_path)
    os.environ["HPCM_INNER_IMPORT"] = "1"
    os.environ["HPCM_TASK"] = task_path
    sys.path.insert(0, d["code_dir"])
    import inner
    from ansys.aedt.core import Desktop
    desk = Desktop(version=version or None, non_graphical=True, new_desktop=True, close_on_exit=True)
    try:
        inner.main(desk.odesktop)
    finally:
        try:
            desk.release_desktop(close_projects=True, close_on_exit=True)
        except Exception:
            pass


def status(work):
    print("work folder: %s" % work)
    for motor in MOTORS:
        st = read_json(os.path.join(work, motor, "state.json"))
        if not st:
            print("%-6s not started" % motor)
            continue
        parts = []
        for tid, t in sorted(st["tasks"].items()):
            lt = t.get("last_try", {})
            parts.append("%s=%s%s" % (tid, t["status"], "(try %d)" % t["attempts"] if t.get("attempts", 0) > 1 else ""))
        print("%-6s %s | updated %s | jobs %s | level floor %s" % (motor, ", ".join(parts), st.get("updated"),
                                                                   ",".join(st.get("jobs", [])[-3:]),
                                                                   LEVELS[st.get("level_floor", 0)]["name"]))
    if os.path.isfile(os.path.join(work, "RESULTS.txt")):
        print()
        print(open(os.path.join(work, "RESULTS.txt")).read())


def main():
    ap = argparse.ArgumentParser(description="Full-motor Maxwell solves of the PCB motors on the UCT HPC")
    ap.add_argument("--mode", default="static",
                    choices=["smoke", "pilot", "static", "transient", "full", "friday", "lab", "report", "status"],
                    help="smoke | pilot | static (sweep) | transient (Rev0 one band / Rev1 two bands) | full (both) | "
                         "friday (fast package: Rev0 + Rev1-S, 2-angle statics then rotating runs at 45 steps over one "
                         "period, cores 24 + 40; Rev2-S / Rev1-D by name, static only)")
    ap.add_argument("--motor", default="ALL", choices=MOTORS + ["ALL"] + LAB_PROFILES,
                    help="ALL = Rev0 + Rev1S (the priority pair); Rev1D and Rev2S only by name")
    ap.add_argument("--angles", type=int, default=4, help="rotor angles over one 7.5 deg ripple period (default 4)")
    ap.add_argument("--ipk", type=float, default=1.0, help="phase current amplitude, A (references use 1 A)")
    ap.add_argument("--padding", type=float, default=20.0, help="air-region padding for the solve, mm (refs: 20)")
    ap.add_argument("--rpm", type=float, default=1000.0, help="prescribed speed of the transient runs")
    ap.add_argument("--rev1-ntasks", type=int, default=None, help="cores for the Rev1-S / Rev1-D / Rev2-S jobs "
                                                                 "(default 40 = the UCT per-job maximum)")
    ap.add_argument("--start-level", type=int, default=None, help="static solver ladder start level 0-5 (default 0; friday 2)")
    ap.add_argument("--tr-runs", default="both", choices=["both", "noload", "load"], help="transient production runs")
    ap.add_argument("--tr-spp", type=int, default=None, help="transient steps per electrical period (default 90 Rev0 / 45 Rev1)")
    ap.add_argument("--tr-periods", type=float, default=None, help="electrical periods simulated (default 1.25)")
    ap.add_argument("--work", default=None)
    ap.add_argument("--disk-gb", type=float, default=45.0,
                    help="disk budget for the whole work folder, GB (UCT /scratch quota is 50 GB; default 45)")
    ap.add_argument("--resized", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--allow-fanout", action="store_true",
                    help="--motor ALL: let this job submit the other motors' jobs itself (off by default)")
    ap.add_argument("--allow-no-quota", action="store_true",
                    help="run even if the account-wide /scratch quota cannot be read (work-folder budget only)")
    ap.add_argument("--max-resubmits", type=int, default=None,
                    help="automatic continuation jobs per motor at the wall-time limit (default 2; 0 = never, "
                         "print the command instead)")
    ap.add_argument("--allow-pip", action="store_true",
                    help="allow pip install --user pyaedt as the last launch fallback (check with the HPC admins first)")
    ap.add_argument("--no-fanout", action="store_true", help="ALL: run the motors one after another in this job")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--local", action="store_true", help="allow running outside a SLURM job (testing only)")
    ap.add_argument("--worker", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--aedt-version", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.mode == "friday":                     # the fast package (all three motors' statics in parallel = 80 cores)
        a.angles = 2                          # 0 and 3.75 deg: half a ripple period apart, the 6th harmonic cancels
        a.friday_cores = {"Rev1S": a.rev1_ntasks or 40, "Rev1D": a.rev1_ntasks or 24, "Rev2S": a.rev1_ntasks or 40}
        a.start_level = 2 if a.start_level is None else a.start_level
        a.tr_spp = a.tr_spp or 45
        a.tr_periods = a.tr_periods or 1.0
    a.rev1_ntasks = a.rev1_ntasks or 40
    if a.rev1_ntasks > MAX_CORES_JOB:
        print("--rev1-ntasks %d is above the %d cores allowed per job - using %d" % (a.rev1_ntasks, MAX_CORES_JOB,
                                                                                   MAX_CORES_JOB))
        a.rev1_ntasks = MAX_CORES_JOB
    if a.mode == "friday":
        a.friday_cores = dict((k, min(v, MAX_CORES_JOB)) for k, v in a.friday_cores.items())
    a.start_level = a.start_level or 0
    if a.worker:
        return worker_main(a.worker, a.aedt_version)
    work = os.path.abspath(a.work or default_work())
    if not os.path.isdir(work):
        os.makedirs(work)
    if a.mode == "status":
        return status(work)
    if a.mode == "report":
        code = extract_payload(work)
        print(build_reports(work, read_json(os.path.join(code, "references.json"), {}), a.ipk))
        return
    if not os.environ.get("SLURM_JOB_ID") and not a.local:
        # login node: nothing is extracted, copied or run here, and nothing is submitted automatically
        print("Not inside a SLURM job, so nothing runs here (UCT HPC: no jobs on the head node).\n"
              "Submit it to the scheduler instead, for example:\n"
              "    sbatch %s %s" % (os.path.basename(sys.argv[0]) or "hpc_motor.py", " ".join(shlex.quote(x) for x in sys.argv[1:])))
        return 1
    code = extract_payload(work)
    script = install_self(work)
    if a.mode == "lab" and a.motor not in LAB_PROFILES:
        print("--mode lab needs --motor <one of %s>" % ", ".join(LAB_PROFILES))
        return 2
    if a.mode != "lab" and a.motor in LAB_PROFILES:
        print("%s is a v10 lab-model profile: use --mode lab --motor %s" % (a.motor, a.motor))
        return 2
    if a.motor == "ALL" and not a.allow_fanout and a.mode != "smoke":
        print("--motor ALL would submit further jobs on its own. Submit each motor yourself instead, e.g.\n"
              "    sbatch hpc_motor.py --mode %s --motor Rev0\n"
              "    sbatch --ntasks=40 hpc_motor.py --mode %s --motor Rev1S\n"
              "(or add --allow-fanout once the runs have been checked)" % (a.mode, a.mode))
        return 2
    motors = ALL_MOTORS if a.motor == "ALL" else [a.motor]
    if a.mode == "smoke":
        motors = ["smoke"]
    first = motors[0]
    LOG.path = os.path.join(work, first if first != "smoke" else "smoke", "supervisor.log")
    if not os.path.isdir(os.path.dirname(LOG.path)):
        os.makedirs(os.path.dirname(LOG.path))
    sup = Supervisor(a, work, code)
    sup.started = time.time()
    sup.job_len = min(sup.deadline - sup.started, 100 * 3600.0) if sup.deadline != float("inf") else 100 * 3600.0
    sup.banner(a.motor, a.mode)
    lines, bad = source_check(code)
    for l in lines:
        LOG("Source check: " + l)
    if bad:
        LOG("Embedded geometry does not match the source package (%s) - stopping before any AEDT work" % bad, "ERROR")
        return 2
    # ALL: one job per motor (independent failures), this job keeps the first one
    if len(motors) > 1 and not a.no_fanout and os.environ.get("SLURM_JOB_ID"):
        fan = read_json(os.path.join(work, "fanout.json"), {})
        keep = []
        for m in motors[1:]:
            stm = read_json(os.path.join(work, m, "state.json"), {})
            if fan.get(m) or (stm and all(t.get("status") == "done" for t in stm.get("tasks", {}).values()) and stm.get("tasks")):
                LOG("Fan-out: %s already has job %s (or is finished) - not submitting again" % (m, fan.get(m)))
                continue
            nt = str(a.rev1_ntasks) if m != "Rev0" else os.environ.get("SLURM_NTASKS", "32")
            if a.mode == "friday" and m != "Rev0":
                nt = str(a.friday_cores[m])
            jid, cmd, out = sup.sbatch(m, a.mode, extra={"--ntasks": nt}, dependency=False)
            if jid:
                fan[m] = jid
                LOG("Fan-out: %s submitted as job %s" % (m, jid))
            else:
                LOG("Fan-out: could not submit %s (%s) - it will run in this job after %s" % (m, out.strip()[:200], first),
                    "WARN")
                keep.append(m)
        atomic_json(os.path.join(work, "fanout.json"), fan)
        motors = [first] + keep
    # a Rev1/Rev2 motor submitted on its own with the header's core count: resubmit itself with the cores it needs
    if (len(motors) == 1 and motors[0] in ("Rev1S", "Rev1D", "Rev2S") and os.environ.get("SLURM_JOB_ID")
            and not a.resized and not a.local):
        want = a.friday_cores[motors[0]] if a.mode == "friday" else a.rev1_ntasks
        if sup.cores < want:
            LOG("%s needs %d cores (%.0f GB of memory) but this job has %d. Stopping before any work - submit it as:\n"
                "    sbatch --ntasks=%d hpc_motor.py %s" % (motors[0], want, want * 7.8, sup.cores, want,
                                                         " ".join(shlex.quote(x) for x in sys.argv[1:])), "ERROR")
            return 4
    if not sup.discover():
        build_reports(work, sup.refs, a.ipk)
        return 3
    for i, m in enumerate(motors):
        name = m if m != "smoke" else "smoke"
        LOG.path = os.path.join(work, name, "supervisor.log")
        sup.mdir(name)
        # one supervisor per motor at a time (a resubmitted job waits for the old one to let go)
        lockf = open(os.path.join(work, name, ".supervisor.lock"), "w")
        t_end = time.time() + 1200
        while True:
            try:
                fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (IOError, OSError):
                if time.time() > t_end:
                    LOG("[%s] another job is working on this motor - leaving it alone" % name, "WARN")
                    lockf = None
                    break
                time.sleep(15)
        if lockf is None:
            continue
        r = sup.run_motor(name, a.mode)
        LOG("[%s] supervisor finished: %s" % (name, r))
        fcntl.flock(lockf, fcntl.LOCK_UN)
        if r in ("resubmitted", "resubmit_failed", "stopped"):
            rest = motors[i + 1:]
            if rest:
                for m2 in rest:
                    jid, cmd, out = sup.sbatch(m2, a.mode)
                    LOG("[%s] queued as job %s so it is not lost" % (m2, jid or "FAILED: " + out.strip()[:200]))
            break
    if a.mode == "smoke":
        st = read_json(os.path.join(work, "smoke", "state.json"), {})
        tk = st.get("tasks", {})
        okp, oks = _get(tk, "probe", "status") == "done", _get(tk, "smoke", "status") == "done"
        okg, okr = _get(tk, "tgate", "status") == "done", _get(tk, "trot", "status") == "done"
        info = st.get("probe") or {}
        lines = ["SMOKE TEST %s" % ("PASSED" if okp and oks and okg and okr else
                                   ("NOT FINISHED - out of wall time; resubmit the same command to continue" if
                                    okp and oks and "failed" not in (_get(tk, "tgate", "status"), _get(tk, "trot", "status"))
                                    else
                                    "PASSED FOR STATIC SOLVES ONLY - TRANSIENT GATES FAILED" if okp and oks else "FAILED")),
                 "  AEDT start + licence + Maxwell design : %s%s" % ("OK" if okp else "FAILED",
                                                                    (" (%s, %s %s)" % (info.get("aedt_version"), info.get("engine"), info.get("python"))) if okp else ""),
                 "  cores setting                         : %s" % (_get(info, "hpc") or "-"),
                 "  one-board build + solve (lab Gate 1)  : %s%s" % ("OK" if oks else "FAILED",
                                                                    (" in %s" % hms(_get(tk, "smoke", "seconds_total") or 0)) if oks else ""),
                 "  transient T-Omega, PCB copper (Gate 2) : %s" % ("OK" if okg else _smoke_state(tk, "tgate")),
                 "  rotating band + motion, one board      : %s" % ("OK" if okr else _smoke_state(tk, "trot")),
                 "  launch mode used                      : %s" % st.get("launch_mode", "script")]
        cpu = [(k, h.get("avg_cores_busy"), h.get("peak_cores_busy_1min", "?"), h.get("cores_allocated"), h.get("seconds"))
               for k in ("smoke", "tgate", "trot") for h in (_get(tk, k, "history") or [])[-1:] if h.get("outcome") == "ok"]
        lines.append("  CPU use (avg / busiest minute / alloc): %s" % (", ".join(
            "%s %s/%s/%s in %ss" % c for c in cpu) or "-"))
        q = scratch_quota()
        lines.append("  account-wide /scratch quota readable  : %s" % (
            ("yes, %.1f of %.0f GB used" % (q[1] / 2.0 ** 30, q[0] / 2.0 ** 30)) if q else
            "NO - production runs will refuse to start (ask the HPC team; --allow-no-quota overrides)"))
        lines.append("  AEDT temporary folder                 : %s" % getattr(sup, "tmpdir", "-"))
        for k in ("probe", "smoke", "tgate", "trot"):
            if _get(tk, k, "status") == "failed":
                lines.append("  %s failed: %s" % (k, (_get(tk, k, "why") or "")[:500]))
        if okp and oks and not (okg and okr):
            lines.append("Static solves are ready; the transient stages are NOT (see above) - static/pilot only for now.")
        lines.append("Next: sbatch hpc_motor.py --mode friday --motor Rev0" if okp and oks else
                     "Next: read %s and the task folders under smoke/tasks/ (aedt.log, progress.txt)" % LOG.path)
        with open(os.path.join(work, "SMOKE_RESULT.txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        LOG("\n" + "\n".join(lines))
        return 0 if okp and oks and okg and okr else 1
    if a.mode == "lab":
        st = read_json(os.path.join(work, a.motor, "state.json"), {})
        t = st.get("tasks", {}).get("lab", {})
        LOG("[%s] lab model run: %s%s" % (a.motor, t.get("status", "?"), (" - " + t.get("why", "")) if t.get("why") else ""))
        return 0 if t.get("status") == "done" else 1
    txt = build_reports(work, sup.refs, a.ipk)
    LOG("Summary (also in %s):\n%s" % (os.path.join(work, "RESULTS.txt"), txt))
    return 0


def _smoke_state(tk, k):
    st = _get(tk, k, "status")
    return "FAILED" if st == "failed" else "NOT RUN YET (job ran out of wall time - nothing wrong)"


ANIMATION_HELPER = r'''"""Turn the transient field exports into frames and a GIF (run on your own PC: needs numpy + matplotlib).
    python make_field_animation.py <folder with B_*.fld / J_*.fld files> [B_S1]
Each B_<plane>_t<time>ms.fld file holds x y z Bx By Bz on a polar grid at mid-gap (one file per saved time step)."""
import glob, os, re, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

folder = sys.argv[1] if len(sys.argv) > 1 else "."
prefix = sys.argv[2] if len(sys.argv) > 2 else "B_S1"
files = sorted(glob.glob(os.path.join(folder, prefix + "_t*ms.fld")),
               key=lambda p: float(re.search(r"_t([0-9.]+)ms", p).group(1)))
if not files:
    sys.exit("no %s_t*ms.fld files in %s" % (prefix, folder))

def load(p):
    rows = []
    for line in open(p):
        v = line.replace(",", " ").split()
        try:
            rows.append([float(x) for x in v[:6]])
        except ValueError:
            pass
    a = np.array([r for r in rows if len(r) == 6])
    s = 1e3 if np.abs(a[:, :2]).max() < 1.0 else 1.0          # echoed points in m or mm
    return a[:, 0] * s, a[:, 1] * s, a[:, 3:6]

frames = [load(p) for p in files]
times = [float(re.search(r"_t([0-9.]+)ms", p).group(1)) for p in files]
comp = "J" if prefix.startswith("J") else "B"
val = [np.linalg.norm(f[2], axis=1) if comp == "J" else f[2][:, 2] for f in frames]
lim = max(np.abs(v).max() for v in val)
fig, ax = plt.subplots(figsize=(6, 6))
os.makedirs(os.path.join(folder, prefix + "_frames"), exist_ok=True)

def draw(i):
    ax.clear()
    x, y, _ = frames[i]
    sc = ax.scatter(x, y, c=val[i], s=6, cmap="RdBu_r" if comp == "B" else "inferno",
                    vmin=-lim if comp == "B" else 0, vmax=lim)
    ax.set_aspect("equal"); ax.set_xlabel("x (mm)"); ax.set_ylabel("y (mm)")
    ax.set_title("%s  %s  t = %.3f ms" % (prefix, "Bz (T)" if comp == "B" else "|J| (A/m^2)", times[i]))
    return sc,

for i in range(len(frames)):
    draw(i)
    fig.savefig(os.path.join(folder, prefix + "_frames", "frame_%03d.png" % i), dpi=150)
FuncAnimation(fig, draw, frames=len(frames), interval=150).save(os.path.join(folder, prefix + ".gif"),
                                                                writer=PillowWriter(fps=8))
print("wrote %d frames and %s.gif" % (len(frames), prefix))
'''


PAYLOAD_SHA256 = "__PAYLOAD_SHA256__"
PAYLOAD_B64 = """__PAYLOAD_B64__"""

if __name__ == "__main__":
    sys.exit(main() or 0)
