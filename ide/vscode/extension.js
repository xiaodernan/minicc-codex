const vscode = require("vscode");

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("minicc.openWorkbench", async () => {
      const url = vscode.workspace.getConfiguration("minicc").get("workbenchUrl") || "http://127.0.0.1:8765";
      await vscode.env.openExternal(vscode.Uri.parse(String(url)));
    }),
    vscode.commands.registerCommand("minicc.sendSelection", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("minicc: no active editor");
        return;
      }
      const selected = editor.document.getText(editor.selection);
      const text = selected || editor.document.getText();
      await vscode.env.clipboard.writeText(text);
      vscode.window.showInformationMessage("minicc: selection copied — paste it into the workbench");
    }),
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
