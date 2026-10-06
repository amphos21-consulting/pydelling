// Sidebar controls to collapse/expand all nested sections in the primary nav.
(function () {
  function getSidebarProjectLabel() {
    const version = typeof window.__PYDELLING_VERSION__ === 'string'
      ? window.__PYDELLING_VERSION__.trim()
      : '';

    return version ? `pydelling ${version}` : 'pydelling';
  }

  function getPrimarySidebarNav() {
    return document.querySelector('.md-sidebar--primary .md-nav--primary');
  }

  function setPrimarySidebarTitle() {
    const root = getPrimarySidebarNav();
    if (!root) return;

    const title = root.querySelector(':scope > .md-nav__title');
    if (!title) return;

    const logoButton = title.querySelector('.md-nav__button.md-logo');
    title.textContent = '';

    if (logoButton) {
      title.appendChild(logoButton);
      title.appendChild(document.createTextNode(' '));
    }

    title.appendChild(document.createTextNode(getSidebarProjectLabel()));
  }

  function getNestedToggles(root) {
    return root.querySelectorAll(':scope .md-nav__item--nested > input.md-nav__toggle[id]');
  }

  function isToggleExpanded(toggle) {
    if (toggle.checked) return true;
    if (toggle.classList.contains('md-toggle--indeterminate')) return true;

    const parentItem = toggle.closest('.md-nav__item--nested');
    const childNav = parentItem && parentItem.querySelector(':scope > nav.md-nav');
    if (childNav && childNav.getAttribute('aria-expanded') === 'true') return true;

    return false;
  }

  function collapseByDefault() {
    const root = getPrimarySidebarNav();
    if (!root) return;

    const toggles = getNestedToggles(root);
    toggles.forEach((toggle) => {
      const parentItem = toggle.closest('.md-nav__item');
      const isActive = parentItem && parentItem.classList.contains('md-nav__item--active');
      if (!isActive && isToggleExpanded(toggle)) {
        clickToggleLabel(toggle);
      }
    });
  }

  function enforceCollapsedAfterHydration() {
    // Material can restore nav state asynchronously; enforce collapse after init.
    collapseByDefault();
    requestAnimationFrame(collapseByDefault);
    setTimeout(collapseByDefault, 120);
    setTimeout(collapseByDefault, 320);
  }

  function clickToggleLabel(toggle) {
    const id = toggle.getAttribute('id');
    if (!id) return;
    const label = toggle.parentElement && toggle.parentElement.querySelector('label[for="' + id + '"]');
    if (label) {
      label.click();
    }
  }

  function setAllNavToggles(open) {
    const root = getPrimarySidebarNav();
    if (!root) return;

    const toggles = getNestedToggles(root);
    toggles.forEach((toggle) => {
      // Keep the active section untouched when collapsing so users do not lose context.
      const parentItem = toggle.closest('.md-nav__item');
      const isActive = parentItem && parentItem.classList.contains('md-nav__item--active');
      if (!open && isActive) return;

      const expanded = isToggleExpanded(toggle);

      if (open && !expanded) {
        clickToggleLabel(toggle);
      }
      if (!open && expanded) {
        clickToggleLabel(toggle);
      }
    });
  }

  function createMaterialSymbol(iconName) {
    const span = document.createElement('span');
    span.className = 'material-symbols-outlined';
    span.setAttribute('aria-hidden', 'true');
    span.textContent = iconName;
    return span;
  }

  function createIconButton(title, iconName, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sidebar-icon-button';
    button.title = title;
    button.setAttribute('aria-label', title);
    button.appendChild(createMaterialSymbol(iconName));
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      onClick();
    });
    return button;
  }

  function buildControls() {
    const root = getPrimarySidebarNav();
    if (!root) return;
    if (root.querySelector('.sidebar-nav-controls')) return;

    const controls = document.createElement('div');
    controls.className = 'sidebar-nav-controls';

    const collapseButton = createIconButton(
      'Collapse all sections',
      'unfold_less',
      () => setAllNavToggles(false)
    );

    const expandButton = createIconButton(
      'Expand all sections',
      'unfold_more',
      () => setAllNavToggles(true)
    );

    controls.appendChild(collapseButton);
    controls.appendChild(expandButton);

    const title = root.querySelector(':scope > .md-nav__title');
    if (title && title.parentElement === root) {
      root.insertBefore(controls, title.nextElementSibling);
    } else {
      root.insertBefore(controls, root.firstChild);
    }
  }

  function init() {
    setPrimarySidebarTitle();
    buildControls();
    enforceCollapsedAfterHydration();
  }

  document.addEventListener('DOMContentLoaded', init);
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(init);
  }
})();
