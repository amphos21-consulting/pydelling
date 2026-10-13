// Enhanced anchor navigation fix for mkdocs with mkdocstrings
document.addEventListener('DOMContentLoaded', function() {
    
    // Function to scroll to anchor with proper offset
    function scrollToAnchor(anchorId) {
        const target = document.getElementById(anchorId) || document.querySelector(`[id="${anchorId}"]`);
        if (target) {
            const headerOffset = 80;
            const elementPosition = target.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
            return true;
        }
        return false;
    }

    // Function to wait for content to load and then scroll
    function waitAndScroll(anchorId, maxAttempts = 20) {
        let attempts = 0;
        
        const tryScroll = () => {
            attempts++;
            if (scrollToAnchor(anchorId)) {
                return; // Success
            }
            
            if (attempts < maxAttempts) {
                setTimeout(tryScroll, 100); // Try again after 100ms
            }
        };
        
        tryScroll();
    }

    // Handle hash change events (when clicking navigation links)
    window.addEventListener('hashchange', function() {
        const hash = window.location.hash;
        if (hash && hash.length > 1) {
            const anchorId = hash.substring(1);
            setTimeout(() => waitAndScroll(anchorId), 50);
        }
    });

    // Handle initial page load with hash
    if (window.location.hash) {
        const anchorId = window.location.hash.substring(1);
        setTimeout(() => waitAndScroll(anchorId), 200);
    }

    // Handle navigation panel clicks specifically
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a[href*="#"]');
        if (link && link.classList.contains('md-nav__link')) {
            const href = link.getAttribute('href');
            if (href && href.includes('#')) {
                const anchorId = href.split('#')[1];
                if (anchorId) {
                    // Don't prevent default, let the URL change naturally
                    setTimeout(() => waitAndScroll(anchorId), 100);
                }
            }
        }
    });

    // Observer to watch for content changes (mkdocstrings loading)
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                // Check if hash exists and try to scroll after content changes
                if (window.location.hash) {
                    const anchorId = window.location.hash.substring(1);
                    setTimeout(() => scrollToAnchor(anchorId), 100);
                }
            }
        });
    });

    // Start observing the document body for changes
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    // Additional fix for Material theme - ensure TOC is properly connected
    setTimeout(function() {
        // Add scroll margin to all elements with IDs
        document.querySelectorAll('[id]').forEach(function(element) {
            element.style.scrollMarginTop = '80px';
        });
    }, 500);
});