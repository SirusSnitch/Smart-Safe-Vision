document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const openMobileMenu = document.getElementById('open-mobile-menu');
    const closeMobileMenu = document.getElementById('close-mobile-menu');
    const mobileMenu = document.getElementById('mobile-menu');

    if (openMobileMenu && closeMobileMenu && mobileMenu) {
        openMobileMenu.addEventListener('click', () => {
            mobileMenu.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        });

        closeMobileMenu.addEventListener('click', () => {
            mobileMenu.classList.add('hidden');
            document.body.style.overflow = '';
        });
    }

    // User dropdown toggle
    const userMenuButton = document.getElementById('user-menu-button');
    const userDropdown = document.getElementById('user-dropdown');

    if (userMenuButton && userDropdown) {
        userMenuButton.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdown.classList.toggle('hidden');
        });
    }

    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
        if (userDropdown && !userDropdown.contains(e.target) && !userMenuButton.contains(e.target)) {
            userDropdown.classList.add('hidden');
        }
    });

    // Dropdown menu toggles
    document.querySelectorAll('.dropdown-toggle').forEach(button => {
        button.addEventListener('click', function() {
            this.classList.toggle('active');
        });
    });

    // Add active class to current page link
    const currentPath = window.location.pathname;
    document.querySelectorAll('nav a').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('bg-blue-50', 'text-blue-600');
        }
    });
});