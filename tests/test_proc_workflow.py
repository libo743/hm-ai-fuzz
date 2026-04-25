from __future__ import annotations

from pathlib import Path

from core.pipeline import WorkflowPipeline
from core.protocols import WorkflowContext
from extractors.proc.extractor import ProcDiscoverPlugin
from extractors.proc.source_index import SourceIndex
from generators.syzkaller.minimal import MinimalSyzkallerGeneratePlugin
from modelers.simple_diff import SimpleDiffPlugin
from validators.syzkaller_build import SyzkallerBuildValidatePlugin


def test_auto_scan_skips_irrelevant_trees_but_full_mode_can_find_them(tmp_path: Path) -> None:
    kernel = tmp_path / "linux"
    (kernel / "drivers" / "misc").mkdir(parents=True)
    (kernel / "drivers" / "misc" / "totally_unrelated.c").write_text(
        """
        static const struct proc_ops secret_ops = {
            .proc_read = seq_read,
        };
        static int init_secret(void)
        {
            proc_create("secretnode", 0444, NULL, &secret_ops);
            return 0;
        }
        """,
        encoding="utf-8",
    )

    auto_index = SourceIndex(kernel, scan_mode="auto", proc_paths=["/proc/secretnode"]).build()
    full_index = SourceIndex(kernel, scan_mode="full", proc_paths=["/proc/secretnode"]).build()

    assert len(auto_index.registrations) == 0
    assert len(full_index.registrations) == 1


def test_proc_discover_plugin_filters_by_target_module(tmp_path: Path) -> None:
    kernel = tmp_path / "linux"
    (kernel / "fs" / "proc").mkdir(parents=True)
    (kernel / "drivers" / "misc").mkdir(parents=True)
    (kernel / "fs" / "proc" / "alpha.c").write_text(
        """
        static const struct proc_ops alpha_ops = {
            .proc_read = seq_read,
            .proc_write = alpha_write,
        };

        static int alpha_init(void)
        {
            proc_create("alpha", 0644, NULL, &alpha_ops);
            return 0;
        }
        """,
        encoding="utf-8",
    )
    (kernel / "drivers" / "misc" / "beta.c").write_text(
        """
        static const struct proc_ops beta_ops = {
            .proc_read = seq_read,
        };

        static int beta_init(void)
        {
            proc_create("beta", 0444, NULL, &beta_ops);
            return 0;
        }
        """,
        encoding="utf-8",
    )

    ctx = WorkflowContext(
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        kernel_src=kernel,
        config={"target_module": "fs/proc", "search_method": "prefix", "scan_mode": "full"},
    )
    discover = ProcDiscoverPlugin().discover(ctx)

    assert len(discover) == 1
    assert discover[0].target == "/proc/alpha"
    assert discover[0].metadata["module_file"] == "fs/proc/alpha.c"
    assert discover[0].capabilities == ["open", "read", "write", "lseek"]


def test_diff_plugin_treats_all_interfaces_as_new_against_empty_json(tmp_path: Path) -> None:
    discover = [
        {
            "subsystem": "proc",
            "target": "/proc/alpha",
            "kind": "virtual_file",
            "capabilities": ["open", "read", "write"],
            "metadata": {"node_type": "file", "module_file": "fs/proc/alpha.c", "registration_kind": "proc_create"},
            "source": {"file": "fs/proc/alpha.c", "line": 12, "symbol": "alpha_ops"},
        },
        {
            "subsystem": "proc",
            "target": "/proc/bus",
            "kind": "virtual_dir",
            "capabilities": ["open", "getdents64"],
            "metadata": {"node_type": "dir", "module_file": "fs/proc/root.c", "registration_kind": "proc_mkdir"},
            "source": {"file": "fs/proc/root.c", "line": 33, "symbol": None},
        },
    ]

    script_ctx = WorkflowContext(workspace=tmp_path, output_dir=tmp_path / "out")
    from core.schemas import InterfaceSpec, SourceRef

    current_specs = [
        InterfaceSpec(
            subsystem=item["subsystem"],
            target=item["target"],
            kind=item["kind"],
            capabilities=item["capabilities"],
            source=SourceRef(**item["source"]),
            metadata=item["metadata"],
        )
        for item in discover
    ]
    diff = SimpleDiffPlugin().diff(current_specs, {}, script_ctx)

    assert len(diff.existing_keys) == 0
    assert len(diff.new_items) == 5
    assert diff.new_items[0]["suggested_case_file"] == "proc_alpha__open.json"
    assert {item["op"] for item in diff.new_items if item["target"] == "/proc/alpha"} == {
        "open",
        "read",
        "write",
    }


def test_generate_plugin_writes_minimal_proc_auto_txt(tmp_path: Path) -> None:
    from core.schemas import DiffResult

    diff = DiffResult(
        new_items=[
            {"subsystem": "proc", "target": "/proc/alpha", "op": "open", "node_type": "file"},
            {"subsystem": "proc", "target": "/proc/alpha", "op": "read", "node_type": "file"},
            {"subsystem": "proc", "target": "/proc/alpha", "op": "write", "node_type": "file"},
            {"subsystem": "proc", "target": "/proc/bus", "op": "open", "node_type": "dir"},
            {"subsystem": "proc", "target": "/proc/bus", "op": "getdents64", "node_type": "dir"},
            {"subsystem": "proc", "target": "/proc/alpha", "op": "ioctl", "node_type": "file"},
            {"subsystem": "proc", "target": "/proc/alpha", "op": "poll", "node_type": "file"},
            {"subsystem": "proc", "target": "/proc/vmcore", "op": "open", "node_type": "file"},
            {"subsystem": "proc", "target": "/proc/vmcore", "op": "mmap", "node_type": "file"},
        ]
    )
    syzkaller = tmp_path / "syzkaller"
    (syzkaller / "sys" / "linux").mkdir(parents=True)
    ctx = WorkflowContext(workspace=tmp_path, output_dir=tmp_path / "out", syzkaller_dir=syzkaller)

    generation = MinimalSyzkallerGeneratePlugin().generate(diff, ctx)

    txt = (syzkaller / "sys" / "linux" / "proc_auto.txt").read_text(encoding="utf-8")
    const = (syzkaller / "sys" / "linux" / "proc_auto.txt.const").read_text(encoding="utf-8")
    assert "resource fd_proc_proc_alpha[fd]" in txt
    assert 'openat$proc_proc_alpha(fd const[AT_FDCWD], file ptr[in, string["/proc/alpha"]]' in txt
    assert "read$proc_proc_alpha(fd fd_proc_proc_alpha, buf buffer[out], count len[buf])" in txt
    assert "write$proc_proc_alpha(fd fd_proc_proc_alpha, buf buffer[in], count len[buf])" in txt
    assert "ioctl$proc_proc_alpha(fd fd_proc_proc_alpha, cmd int32, arg buffer[in])" in txt
    assert "pollfd$proc_proc_alpha {" in txt
    assert "poll$proc_proc_alpha(ufds ptr[inout, pollfd$proc_proc_alpha], nfds len[ufds], timeout_msecs int32)" in txt
    assert 'openat$proc_proc_bus(fd const[AT_FDCWD], file ptr[in, string["/proc/bus"]]' in txt
    assert "mmap$proc_proc_vmcore(addr vma, len len[addr], prot flags[mmap_prot], flags flags[mmap_flags], fd fd_proc_proc_vmcore, offset intptr[0:0xffffffff, 0x1000])" in txt
    assert "arches = 386, amd64, arm, arm64, mips64le, ppc64le, riscv64, s390x" in const
    assert "__NR_openat =" in const
    assert generation.metadata["generated_interface_count"] == 3


def test_validate_plugin_reports_success(tmp_path: Path) -> None:
    from core.schemas import GeneratedFile, GenerationResult

    syzkaller = tmp_path / "syzkaller"
    syzkaller.mkdir(parents=True)
    (syzkaller / "Makefile").write_text("descriptions:\n\t@echo descriptions ok\n", encoding="utf-8")
    tracked = syzkaller / "sys" / "linux" / "proc_auto.txt"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("# generated\n", encoding="utf-8")

    generation = GenerationResult(generated_files=[GeneratedFile(path=str(tracked), kind="txt", details={"entry_count": 1})])
    ctx = WorkflowContext(
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        syzkaller_dir=syzkaller,
        config={"make_target": "descriptions", "timeout_sec": 30},
    )

    validation = SyzkallerBuildValidatePlugin().validate(generation, ctx)

    assert validation.status == "passed"
    assert validation.diagnostics == []


def test_proc_workflow_runs_end_to_end(tmp_path: Path) -> None:
    kernel = tmp_path / "linux"
    syzkaller = tmp_path / "syzkaller"
    (kernel / "fs" / "proc").mkdir(parents=True)
    (syzkaller / "sys" / "linux").mkdir(parents=True)
    (syzkaller / "Makefile").write_text("descriptions:\n\t@echo descriptions ok\n", encoding="utf-8")
    (kernel / "fs" / "proc" / "alpha.c").write_text(
        """
        static const struct proc_ops alpha_ops = {
            .proc_read = seq_read,
            .proc_write = alpha_write,
        };

        static int alpha_init(void)
        {
            proc_create("alpha", 0644, NULL, &alpha_ops);
            return 0;
        }
        """,
        encoding="utf-8",
    )

    ctx = WorkflowContext(
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        kernel_src=kernel,
        syzkaller_dir=syzkaller,
        config={
            "target_module": "fs/proc",
            "search_method": "prefix",
            "scan_mode": "full",
            "txt_name": "proc_auto.txt",
            "make_target": "descriptions",
            "timeout_sec": 30,
        },
    )

    result = WorkflowPipeline(
        discover_plugin=ProcDiscoverPlugin(),
        diff_plugin=SimpleDiffPlugin(),
        generate_plugin=MinimalSyzkallerGeneratePlugin(),
        validate_plugin=SyzkallerBuildValidatePlugin(),
    ).run(ctx, existing={})

    assert len(result["discover"]) == 1
    assert len(result["diff"]["new_items"]) == 4
    assert result["validate"]["status"] == "passed"
