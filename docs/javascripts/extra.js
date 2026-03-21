// Extra JavaScript for SolidWorks MCP documentation

function enhancePage(root) {
    addCopyButtons();
    addStatusIndicators();
    enhanceBadges();
    enhanceNavigation();
}

if (typeof document$ !== 'undefined') {
    document$.subscribe(function() {
        enhancePage(document);
    });
} else {
    document.addEventListener('DOMContentLoaded', function() {
        enhancePage(document);
    });
}

function addCopyButtons() {
    // Add copy buttons to all code blocks
    const codeBlocks = document.querySelectorAll('pre code');
    
    codeBlocks.forEach(function(codeBlock) {
        const pre = codeBlock.parentNode;
        if (pre.querySelector('.copy-button')) return; // Already has button
        
        const button = document.createElement('button');
        button.className = 'copy-button';
        button.textContent = '📋';
        button.title = 'Copy to clipboard';
        
        button.addEventListener('click', function() {
            navigator.clipboard.writeText(codeBlock.textContent).then(function() {
                button.textContent = '✅';
                setTimeout(function() {
                    button.textContent = '📋';
                }, 1000);
            });
        });
        
        pre.style.position = 'relative';
        pre.appendChild(button);
    });
}

function addStatusIndicators() {
    // Add visual indicators for different statuses
    const statusElements = document.querySelectorAll('[data-status]');
    
    statusElements.forEach(function(element) {
        const status = element.getAttribute('data-status');
        element.classList.add('status-' + status);
    });
}

function enhanceBadges() {
    // Ensure shields.io badges are properly loaded and styled
    const badges = document.querySelectorAll('img[src*="shields.io"], img[src*="img.shields.io"]');
    
    badges.forEach(function(badge) {
        // Add loading error fallback
        badge.addEventListener('error', function() {
            console.warn('Badge failed to load:', badge.src);
        });
        
        // Add proper alt text if missing
        if (!badge.alt || badge.alt.trim() === '') {
            badge.alt = 'Status Badge';
        }
        
        // Ensure badges are inline
        badge.style.display = 'inline-block';
        badge.style.marginRight = '4px';
    });
    
    // Force reload any badges that might have failed
    setTimeout(function() {
        badges.forEach(function(badge) {
            if (!badge.complete || badge.naturalHeight === 0) {
                const src = badge.src;
                badge.src = '';
                badge.src = src;
            }
        });
    }, 1000);
}

function enhanceNavigation() {
    // Add smooth scrolling to anchor links
    const anchorLinks = document.querySelectorAll('a[href*="#"]');
    
    anchorLinks.forEach(function(link) {
        link.addEventListener('click', function(e) {
            const href = link.getAttribute('href');
            if (href.startsWith('#')) {
                const target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    });
}

// Add MathJax configuration for math equations
window.MathJax = {
    tex: {
        inlineMath: [["\\(", "\\)"]],
        displayMath: [["\\[", "\\]"]],
        processEscapes: true,
        processEnvironments: true
    },
    options: {
        ignoreHtmlClass: ".*|",
        processHtmlClass: "arithmatex"
    }
};

// Tool category color mapping
const toolCategories = {
    'modeling': '#1976d2',
    'sketching': '#7b1fa2',
    'drawing': '#388e3c',
    'analysis': '#f57c00',
    'export': '#00796b',
    'vba': '#e91e63',
    'templates': '#5d4037',
    'macros': '#ff5722',
    'automation': '#607d8b',
    'file-management': '#9e9e9e'
};