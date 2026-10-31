Name:           simplepostit
Version:        1.2.5
Release:        1%{?dist}
Summary:        Your pinned Simplenote notes as sticky notes on the desktop
License:        GPL-3.0-or-later
URL:            https://github.com/FrankMncrf/SimplePost-It
Source0:        %{url}/archive/refs/tags/v%{version}/SimplePost-It-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  make
BuildRequires:  python3-pyqt6
Requires:       python3 >= 3.10
# PyQt6 se llama distinto en Fedora y en openSUSE
Requires:       (python3-pyqt6 or python3-PyQt6)

%description
Desktop layer for the Simplenote app: pinned notes appear as sticky notes
that can be arranged, read, checked off and edited without opening
Simplenote. Changes sync back to the Simplenote account. Supports
Markdown, to-do lists, private (blurred) notes and a tray icon that can
keep Simplenote running in the background with its window hidden.

%prep
%autosetup -n SimplePost-It-%{version}

%build

%check
QT_QPA_PLATFORM=offscreen make test

%install
make install DESTDIR=%{buildroot} PREFIX=%{_prefix} LIBDIR=%{_prefix}/lib/simplepostit \
    DOCDIR=%{_docdir}/%{name} LICENSEDIR=%{_licensedir}/%{name}

%files
%{_prefix}/lib/simplepostit/
%{_bindir}/simplepostit
%{_datadir}/applications/simplepostit.desktop
%{_datadir}/icons/hicolor/scalable/apps/simplepostit.svg
%{_docdir}/%{name}/
%{_licensedir}/%{name}/

%changelog
* Sat Oct 31 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.2.5-1
- Editor: separate title field, Private checkbox, checklist button

* Fri Oct 30 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.2.4-1
- Sign in with an emailed code; macOS: notes clickable and draggable, no black outline

* Fri Oct 30 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.2.3-1
- Windows: Microsoft Store Simplenote; usable without Simplenote installed (own sign-in)

* Fri Oct 30 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.2.2-1
- macOS: HTTPS certificates in the app bundle; Simplenote session from the Keychain

* Wed Oct 28 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.2.1-1
- One-line Linux installer; installable on openSUSE (python3-PyQt6)

* Wed Oct 28 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.2.0-1
- Reopen Simplenote hidden when closed; one-line installers for macOS/Windows; Intel macOS build

* Wed Oct 28 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.1.0-1
- Board can be dragged anywhere, reference corner option, follows monitor changes

* Wed Oct 28 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.0.2-1
- Linux: Simplenote starts hidden again at login; closing it no longer leaves zombies

* Wed Oct 28 2026 FrankMncrf <57369835+FrankMncrf@users.noreply.github.com> - 1.0.1-1
- Right-click "Move to trash"; board stays above conky on Linux

* Tue Oct 27 2026 FrankMncrf <frank@simplepostit.invalid> - 1.0.0-1
- First public release
