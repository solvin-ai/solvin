document.addEventListener('DOMContentLoaded', function() {

    // --- Modal Elements ---
    const signInButton = document.getElementById('signin-btn');
    const ssoModal = document.getElementById('sso-modal');
    const modalOverlay = ssoModal.querySelector('.modal-overlay');
    const modalCloseButton = ssoModal.querySelector('.modal-close-btn');

    // --- Function to Open Modal ---
    function openModal() {
        if (ssoModal) {
            ssoModal.classList.add('modal-open');
            // Optional: trap focus within modal for accessibility
            // modalCloseButton.focus(); // Focus the close button first
        }
    }

    // --- Function to Close Modal ---
    function closeModal() {
        if (ssoModal) {
            ssoModal.classList.remove('modal-open');
             // Clear any previous error messages when closing
            const errorMsgElement = document.getElementById('modal-error-msg');
             if (errorMsgElement) {
                 errorMsgElement.textContent = '';
                 errorMsgElement.style.display = 'none';
             }
        }
    }

    // --- Event Listeners ---

    // Open modal when Sign In button is clicked
    if (signInButton) {
        signInButton.addEventListener('click', function(event) {
            event.preventDefault(); // Prevent default link behavior
            openModal();
        });
    }

    // Close modal when the close button is clicked
    if (modalCloseButton) {
        modalCloseButton.addEventListener('click', function(event) {
            event.preventDefault();
            closeModal();
        });
    }

    // Close modal when clicking on the overlay
    if (modalOverlay) {
        modalOverlay.addEventListener('click', function() {
            closeModal();
        });
    }

    // Close modal when pressing the Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && ssoModal.classList.contains('modal-open')) {
            closeModal();
        }
    });

    // --- Placeholder for SSO Button Clicks ---
    // (Firebase logic will go here later)
    const githubBtn = document.getElementById('sso-github-btn');
    const googleBtn = document.getElementById('sso-google-btn');
    const microsoftBtn = document.getElementById('sso-microsoft-btn');
     const modalErrorMsg = document.getElementById('modal-error-msg');

    if (githubBtn) {
        githubBtn.addEventListener('click', () => {
            console.log('GitHub Sign-In Initiated (Placeholder)');
            // Example: modalErrorMsg.textContent = 'GitHub login not implemented yet.'; modalErrorMsg.style.display = 'block';
            // Add Firebase GitHub sign-in logic here
        });
    }
    if (googleBtn) {
        googleBtn.addEventListener('click', () => {
            console.log('Google Sign-In Initiated (Placeholder)');
             // Example: modalErrorMsg.textContent = 'Google login not implemented yet.'; modalErrorMsg.style.display = 'block';
            // Add Firebase Google sign-in logic here
        });
    }
    if (microsoftBtn) {
        microsoftBtn.addEventListener('click', () => {
            console.log('Microsoft Sign-In Initiated (Placeholder)');
            // Example: modalErrorMsg.textContent = 'Microsoft login not implemented yet.'; modalErrorMsg.style.display = 'block';
            // Add Firebase Microsoft sign-in logic here
        });
    }

    // --- (Keep your existing Firebase initialization and auth state change listener here if you have it) ---
    // Example:
    // const firebaseConfig = { /* ... your config ... */ };
    // firebase.initializeApp(firebaseConfig);
    // const auth = firebase.auth();
    // ... rest of your Firebase setup and auth listeners ...

}); // End DOMContentLoaded
