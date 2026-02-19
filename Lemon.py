from pathlib import Path
import subprocess
import sys
import os
import shutil
from textual.app import App, ComposeResult
from textual.widgets import Tree, Header, Footer
from textual.widgets.tree import TreeNode
from textual.screen import ModalScreen
from textual.widgets import Button, Static
from textual.containers import Container


# 修复删除确认弹窗的按钮样式问题
class DeleteConfirmScreen(ModalScreen):
    """删除确认弹窗"""
    def __init__(self, path: Path, *args, **kwargs):
        self.path = path
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Container(
            Static(f"确定要删除\n{self.path.name}？", id="confirm-text"),
            Container(
                # 修复：将secondary改为default（Textual支持的样式）
                Button("取消", variant="default", id="cancel"),
                Button("删除", variant="error", id="delete"),
                id="confirm-buttons"
            ),
            id="confirm-dialog"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            self.dismiss(True)  # 返回True表示确认删除
        else:
            self.dismiss(False)  # 返回False表示取消



class Lemon(App):
    """Lemon 文件管理器 - Ctrl+O打开文件 | F5刷新 | Ctrl+D删除文件/目录"""
    TITLE = "Lemon"
    # 新增Ctrl+D删除快捷键
    BINDINGS = [
        ("f5", "refresh", "刷新"),
        ("ctrl+o", "open_selected", "打开选中文件"),
        ("ctrl+d", "delete_selected", "删除选中项"),  # 新增删除快捷键
        ("q", "quit", "退出")
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Tree("文件系统", id="file_tree")
        yield Footer()

    def on_mount(self) -> None:
        """初始化文件树"""
        self.file_tree = self.query_one("#file_tree", Tree)
        roots = self.get_root_paths()
        for root in roots:
            node = self.file_tree.root.add(label=f"📁 {root}", data=root)
            node.data_is_dir = True
            self.load_children(node, root)

    def get_root_paths(self) -> list[Path]:
        """纯Pathlib自动识别系统根路径"""
        cwd = Path.cwd()
        anchor = cwd.anchor

        roots = []
        if anchor.endswith(":\\"):
            for drive in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                p = Path(f"{drive}:\\")
                if p.exists():
                    roots.append(p)
        else:
            roots.append(Path(anchor))
        return roots

    def load_children(self, node: TreeNode, path: Path):
        """加载/刷新节点子内容"""
        node.remove_children()
        if not path or not path.is_dir():
            return

        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for entry in entries:
                try:
                    if entry.is_dir() and not entry.is_file():
                        child = node.add(label=f"📁 {entry.name}", data=entry)
                        child.data_is_dir = True
                    else:
                        # 文件节点：纯文本 + 禁用展开
                        node.add(label=entry.name, data=entry, allow_expand=False)
                except PermissionError:
                    continue
        except PermissionError:
            node.add(label="[权限不足]", allow_expand=False)
        except Exception as e:
            node.add(label=f"[加载错误: {str(e)[:20]}]", allow_expand=False)

    def on_tree_node_expanded(self, event):
        """展开节点时加载内容"""
        node = event.node
        if hasattr(node, "data_is_dir") and node.data_is_dir and node.data:
            self.load_children(node, node.data)

    def action_refresh(self) -> None:
        """F5刷新核心功能"""
        selected_node = self.file_tree.cursor_node
        
        if selected_node:
            if hasattr(selected_node, "data_is_dir") and selected_node.data_is_dir and selected_node.data:
                self.load_children(selected_node, selected_node.data)
                selected_node.expand()
                self.notify("已刷新目录", title="刷新成功", timeout=1.5)
            elif selected_node.parent and hasattr(selected_node.parent, "data_is_dir"):
                parent_node = selected_node.parent
                self.load_children(parent_node, parent_node.data)
                parent_node.expand()
                self.notify("已刷新父目录", title="刷新成功", timeout=1.5)
        else:
            for root_node in self.file_tree.root.children:
                if hasattr(root_node, "data_is_dir") and root_node.data_is_dir:
                    self.load_children(root_node, root_node.data)
            self.notify("已刷新文件系统", title="刷新成功", timeout=1.5)

    def on_tree_node_double_clicked(self, event):
        """双击仅处理目录展开/折叠，移除文件打开逻辑"""
        node = event.node
        # 仅处理目录的双击展开/折叠
        if hasattr(node, "data_is_dir") and node.data_is_dir and node.data:
            if node.is_expanded:
                node.collapse()
            else:
                node.expand()

    def action_open_selected(self) -> None:
        """Ctrl+O打开选中的文件"""
        # 获取当前选中的节点
        selected_node = self.file_tree.cursor_node
        
        if not selected_node:
            self.notify("未选中任何文件", title="提示", timeout=2.0)
            return
        
        # 校验是否是文件
        if selected_node.data and isinstance(selected_node.data, Path) and selected_node.data.is_file():
            # 调用打开方法
            success = self.open_file(selected_node.data)
            if success:
                self.notify(f"已打开：{selected_node.data.name}", title="成功", timeout=2.0)
            else:
                self.notify(f"打开失败：{selected_node.data.name}", title="错误", timeout=3.0)
        else:
            # 选中的是目录/无效项
            self.notify("请先选中一个文件", title="提示", timeout=2.0)

    def open_file(self, file_path: Path) -> bool:
        """稳定的跨平台文件打开方法"""
        try:
            file_path = file_path.resolve()  # 获取绝对路径
            if sys.platform == "win32":
                # Windows原生方法，最稳定
                os.startfile(file_path)
            elif sys.platform == "linux":
                subprocess.Popen(["xdg-open", str(file_path)], start_new_session=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)], start_new_session=True)
            return True
        except Exception as e:
            # 打印错误信息方便排查
            print(f"打开文件错误：{str(e)}")
            return False

    # 新增删除功能核心方法
    def action_delete_selected(self) -> None:
        """Ctrl+D删除选中的文件/目录"""
        # 获取当前选中的节点
        selected_node = self.file_tree.cursor_node
        
        if not selected_node:
            self.notify("未选中任何文件/目录", title="提示", timeout=2.0)
            return
        
        # 校验选中项是否有效
        if not (selected_node.data and isinstance(selected_node.data, Path) and selected_node.data.exists()):
            self.notify("选中项无效或不存在", title="提示", timeout=2.0)
            return
        
        # 显示确认弹窗
        self.push_screen(DeleteConfirmScreen(selected_node.data), self.handle_delete_confirm)

    def handle_delete_confirm(self, confirmed: bool) -> None:
        """处理删除确认结果"""
        if not confirmed:
            self.notify("已取消删除", title="提示", timeout=1.5)
            return
        
        selected_node = self.file_tree.cursor_node
        path_to_delete = selected_node.data
        
        try:
            # 根据类型执行删除
            if path_to_delete.is_file():
                path_to_delete.unlink()  # 删除文件
            elif path_to_delete.is_dir():
                shutil.rmtree(path_to_delete)  # 删除目录（递归删除）
            
            # 删除成功后刷新父目录并提示
            parent_node = selected_node.parent
            if parent_node and hasattr(parent_node, "data_is_dir"):
                self.load_children(parent_node, parent_node.data)
                parent_node.expand()
            
            self.notify(f"已删除：{path_to_delete.name}", title="删除成功", timeout=2.0)
            
        except PermissionError:
            self.notify("权限不足，无法删除", title="错误", timeout=3.0)
        except FileNotFoundError:
            self.notify("文件/目录不存在", title="错误", timeout=3.0)
        except Exception as e:
            self.notify(f"删除失败：{str(e)[:30]}", title="错误", timeout=3.0)
            print(f"删除错误详情：{str(e)}")


if __name__ == "__main__":
    # 检查Textual依赖
    try:
        from textual import __version__
        print(f"Textual版本：{__version__}")
    except ImportError:
        print("请先安装Textual: pip install textual")
        exit(1)
    
    Lemon().run()
