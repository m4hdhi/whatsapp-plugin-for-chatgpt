// Build with Windows' .NET Framework compiler. No installer engine is installed.
using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Drawing;
using System.Diagnostics;
using System.Web.Script.Serialization;
using Microsoft.Win32;

[assembly: AssemblyTitle("GroupBrief Setup")]
[assembly: AssemblyProduct("GroupBrief")]
[assembly: AssemblyVersion("2.0.0.0")]

static class Setup {
    const string Owner = "5e5297a3-b939-4da5-a047-6a99fc16b732";
    const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\GroupBrief-Desktop";
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 10000000 };
    static string DefaultTarget { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "GroupBrief"); } }
    static string Quote(string value) { if (value.Contains("\"")) throw new Exception(); return "\"" + value + "\""; }
    static string Target(string[] args) {
        int index = Array.IndexOf(args, "--target");
        string result = Path.GetFullPath(index >= 0 ? args[index + 1] : DefaultTarget).TrimEnd(Path.DirectorySeparatorChar);
        string home = Path.GetFullPath(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile)).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!result.StartsWith(home, StringComparison.OrdinalIgnoreCase) || !Path.GetFileName(result).StartsWith("GroupBrief", StringComparison.OrdinalIgnoreCase))
            throw new Exception("Choose a GroupBrief installation folder inside your Windows profile.");
        return result;
    }
    static void CheckRoot(string target, bool requireOwner) {
        if (Directory.Exists(target) && (File.GetAttributes(target) & FileAttributes.ReparsePoint) != 0) throw new Exception("The installation folder must not be a directory link.");
        if (requireOwner && (!File.Exists(Path.Combine(target, ".groupbrief-install")) || File.ReadAllText(Path.Combine(target, ".groupbrief-install")) != Owner))
            throw new Exception("This folder is not an owned GroupBrief installation. Its files were left unchanged.");
        // Check every existing parent too, so an app folder cannot traverse a junction.
        for (var parent = Directory.GetParent(target); parent != null; parent = parent.Parent)
            if (parent.Exists && (parent.Attributes & FileAttributes.ReparsePoint) != 0) throw new Exception("The installation path must not traverse directory links.");
    }
    static string SafeFile(string root, string relative) {
        if (String.IsNullOrEmpty(relative) || Path.IsPathRooted(relative) || relative.Contains(":") || relative.Split('/', '\\').Any(part => part == "..")) throw new Exception("Invalid installer file path.");
        string value = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!value.StartsWith(Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new Exception("Invalid installer file path.");
        return value;
    }
    static void RequireClosed() {
        Mutex mutex;
        if (Mutex.TryOpenExisting("GroupBrief.Desktop", out mutex)) { mutex.Dispose(); throw new Exception("Quit GroupBrief from its system-tray menu, then run setup again."); }
    }
    static void Shortcut(string file, string target, string arguments) {
        Directory.CreateDirectory(Path.GetDirectoryName(file));
        dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        dynamic link = shell.CreateShortcut(file);
        link.TargetPath = target; link.Arguments = arguments; link.WorkingDirectory = Path.GetDirectoryName(target);
        link.Description = "GroupBrief WhatsApp assistant"; link.Save();
    }
    static void Install(string target, bool shortcuts, bool desktop, bool startup, bool register, Action<int> progress) {
        RequireClosed(); CheckRoot(target, Directory.Exists(target));
        string stage = target + ".install-" + Guid.NewGuid().ToString("N");
        string backup = target + ".previous-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss");
        CheckRoot(stage, false);
        Directory.CreateDirectory(stage);
        var files = new List<string>();
        try {
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("GroupBrief.Payload")) {
                using (var hash = SHA256.Create()) {
                    string actual = BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
                    if (actual != Payload.Hash) throw new Exception("The setup download is incomplete or damaged. Download it again.");
                }
                stream.Position = 0;
                using (var archive = new ZipArchive(stream, ZipArchiveMode.Read)) {
                    int index = 0;
                    foreach (var entry in archive.Entries) {
                        string full = SafeFile(stage, entry.FullName);
                        if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(full); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(full));
                        using (var input = entry.Open()) using (var output = new FileStream(full, FileMode.CreateNew, FileAccess.Write)) input.CopyTo(output);
                        files.Add(entry.FullName);
                        progress(++index * 94 / archive.Entries.Count);
                    }
                }
            }
            if (!File.Exists(Path.Combine(stage, "UninstallGroupBrief.exe"))) throw new Exception("The setup is missing its uninstaller. Download the complete installer again.");
            files.Add(".groupbrief-install"); files.Add("installed-files.json");
            File.WriteAllText(Path.Combine(stage, ".groupbrief-install"), Owner);
            File.WriteAllText(Path.Combine(stage, "installed-files.json"), Json.Serialize(files));
            // Every move stays within the explicitly selected GroupBrief app path.
            if (Directory.Exists(target)) { CheckRoot(target, true); CheckRoot(backup, false); Directory.Move(target, backup); }
            try { Directory.Move(stage, target); }
            catch { if (Directory.Exists(backup) && !Directory.Exists(target)) Directory.Move(backup, target); throw; }
            string exe = Path.Combine(target, "GroupBrief.exe");
            if (shortcuts) {
                Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "GroupBrief.lnk"), exe, "");
                if (desktop) Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "GroupBrief.lnk"), exe, "");
                if (startup) Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), "GroupBrief.lnk"), exe, "--background");
            }
            if (register) using (var key = Registry.CurrentUser.CreateSubKey(RegistryPath)) {
                key.SetValue("DisplayName", "GroupBrief"); key.SetValue("DisplayVersion", "2.0.0"); key.SetValue("Publisher", "GroupBrief");
                key.SetValue("InstallLocation", target); key.SetValue("DisplayIcon", exe);
                key.SetValue("UninstallString", Quote(Path.Combine(target, "UninstallGroupBrief.exe")) + " --uninstall --target " + Quote(target));
                key.SetValue("NoModify", 1); key.SetValue("NoRepair", 1);
            }
            progress(100);
        } catch {
            // Leave any interrupted staging directory for inspection; never delete personal files on failure.
            throw;
        }
    }
    static void RemoveShortcut(string file, string target) {
        if (!File.Exists(file)) return;
        dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        dynamic link = shell.CreateShortcut(file);
        if (String.Equals((string)link.TargetPath, Path.Combine(target, "GroupBrief.exe"), StringComparison.OrdinalIgnoreCase)) File.Delete(file);
    }
    static void Uninstall(string target) {
        RequireClosed(); CheckRoot(target, true);
        string[] files = Json.Deserialize<string[]>(File.ReadAllText(Path.Combine(target, "installed-files.json")));
        var directories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string relative in files) {
            string file = SafeFile(target, relative);
            bool linked = false;
            for (var parent = Directory.GetParent(file); parent != null && parent.FullName.Length >= target.Length; parent = parent.Parent) {
                if (parent.Exists && (parent.Attributes & FileAttributes.ReparsePoint) != 0) linked = true;
                directories.Add(parent.FullName);
            }
            if (!linked && File.Exists(file)) File.Delete(file);
        }
        foreach (string directory in directories.OrderByDescending(value => value.Length))
            if (Directory.Exists(directory) && !Directory.EnumerateFileSystemEntries(directory).Any()) Directory.Delete(directory, false);
        using (var key = Registry.CurrentUser.OpenSubKey(RegistryPath)) {
            if (key != null && String.Equals((string)key.GetValue("InstallLocation"), target, StringComparison.OrdinalIgnoreCase)) Registry.CurrentUser.DeleteSubKeyTree(RegistryPath, false);
        }
        foreach (var folder in new[] { Environment.SpecialFolder.DesktopDirectory, Environment.SpecialFolder.Programs, Environment.SpecialFolder.Startup })
            RemoveShortcut(Path.Combine(Environment.GetFolderPath(folder), "GroupBrief.lnk"), target);
        // AppData\Local\GroupBrief contains user data and is intentionally untouched.
    }
    [STAThread] static int Main(string[] args) {
#if UNINSTALL_ONLY
        if (!args.Contains("--uninstall-worker") && !args.Contains("--uninstall")) args = args.Concat(new[] { "--uninstall" }).ToArray();
#endif
        bool silent = args.Contains("--silent");
        try {
            string target = Target(args);
            if (args.Contains("--uninstall-worker")) { Thread.Sleep(1200); Uninstall(target); return 0; }
            if (args.Contains("--uninstall")) {
                RequireClosed(); CheckRoot(target, true);
                if (!silent && MessageBox.Show("Remove GroupBrief? Your saved settings, messages and WhatsApp link will be kept on this PC.", "Uninstall GroupBrief", MessageBoxButtons.YesNo) != DialogResult.Yes) return 0;
                string helper = Path.Combine(Path.GetTempPath(), "GroupBrief-Uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
                File.Copy(Assembly.GetExecutingAssembly().Location, helper);
                var worker = Process.Start(new ProcessStartInfo(helper, "--uninstall-worker --silent --target " + Quote(target)) { UseShellExecute = false, CreateNoWindow = true });
                // The installed uninstaller exits so the temporary worker can remove it.
                return 0;
            }
            if (silent) {
                Install(target, !args.Contains("--no-shortcuts"), true, false, !args.Contains("--no-register"), _ => {});
                if (!args.Contains("--no-launch")) Process.Start(Path.Combine(target, "GroupBrief.exe"));
                return 0;
            }
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            var form = new Form { Text = "GroupBrief Setup", ClientSize = new Size(570, 365), FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, StartPosition = FormStartPosition.CenterScreen, Font = new Font("Segoe UI", 10) };
            var heading = new Label { Text = "Install GroupBrief", Font = new Font("Segoe UI", 22, FontStyle.Bold), Left = 26, Top = 23, Width = 520, Height = 50 };
            var detail = new Label { Text = "WhatsApp briefs, personal tasks and reminders on your PC.\nIncludes the local ChatGPT desktop plugin. No Docker setup.", Left = 28, Top = 84, Width = 515, Height = 53 };
            var desktopBox = new CheckBox { Text = "Create a desktop shortcut", Checked = true, Left = 29, Top = 153, Width = 490 };
            var startup = new CheckBox { Text = "Start when I sign in to Windows", Left = 29, Top = 184, Width = 490 };
            var launch = new CheckBox { Text = "Open GroupBrief after installation", Checked = true, Left = 29, Top = 215, Width = 490 };
            var status = new Label { Text = "Only chats you permit are processed. Configure your account in the app.", Left = 29, Top = 252, Width = 515, Height = 35, Font = new Font("Segoe UI", 9) };
            var bar = new ProgressBar { Left = 29, Top = 290, Width = 360, Height = 23, Visible = false };
            var install = new Button { Text = "Install", Left = 416, Top = 303, Width = 125, Height = 38, BackColor = Color.FromArgb(8,119,102), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
            bool done = false, busy = false;
            install.Click += async delegate {
                if (done) { if (launch.Checked) Process.Start(Path.Combine(target, "GroupBrief.exe")); form.Close(); return; }
                install.Enabled = false; desktopBox.Enabled = startup.Enabled = launch.Enabled = false; bar.Visible = true; busy = true;
                status.Text = "Installing the application and its bundled runtime…";
                try {
                    bool desktopValue = desktopBox.Checked, startupValue = startup.Checked;
                    await Task.Run(() => Install(target, true, desktopValue, startupValue, true, value => form.BeginInvoke((Action)(() => bar.Value = value))));
                    status.Text = "Installed. Link WhatsApp and choose your chats in GroupBrief."; done = true; install.Text = "Finish"; launch.Enabled = true;
                } catch (Exception error) { status.Text = error.Message; install.Text = "Retry"; desktopBox.Enabled = startup.Enabled = launch.Enabled = true; }
                finally { busy = false; install.Enabled = true; }
            };
            form.FormClosing += (sender, eventArgs) => { if (busy) eventArgs.Cancel = true; };
            form.Controls.AddRange(new Control[] { heading, detail, desktopBox, startup, launch, status, bar, install });
            Application.Run(form); return 0;
        } catch (Exception error) {
            if (!silent) MessageBox.Show(error.Message, "GroupBrief Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            else Console.Error.WriteLine("GroupBrief setup: " + error.Message);
            return 1;
        }
    }
}
