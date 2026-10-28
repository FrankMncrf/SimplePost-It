Name:           simplepostit
Version:        1.0.0
Release:        1%{?dist}
Summary:        Your pinned Simplenote notes as sticky notes on the desktop
License:        GPL-3.0-or-later
URL:            https://github.com/FrankMncrf/SimplePost-It
Source0:        %{url}/archive/refs/tags/v%{version}/SimplePost-It-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  make
BuildRequires:  python3-pyqt6
Requires:       python3 >= 3.10
Requires:       python3-pyqt6

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
* Tue Oct 27 2026 Frank <frank@simplepostit.invalid> - 1.0.0-1
- First public release
