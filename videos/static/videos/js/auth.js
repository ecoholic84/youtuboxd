/**
 * YouTuBoxd Auth Utilities
 * Handles client-side authentication operations
 */

// Function to clear all client-side caches and storage during logout
function clearClientStorage() {
    // Clear localStorage items that might contain cached data
    localStorage.removeItem('youtuboxd_user_data');
    localStorage.removeItem('youtuboxd_videos');
    localStorage.removeItem('youtuboxd_tags');
    
    // Clear sessionStorage
    sessionStorage.clear();
    
    // Clear any application cache if available
    if (window.caches) {
        caches.keys().then(function(names) {
            for (let name of names) {
                if (name.includes('youtuboxd')) {
                    caches.delete(name);
                }
            }
        });
    }
    
    console.log('Client storage cleared during logout');
    
    // Continue with logout redirect
    return true;
}

// Attach logout handler to any logout buttons
document.addEventListener('DOMContentLoaded', function() {
    const logoutLink = document.querySelector('a[href="/logout/"]');
    
    if (logoutLink) {
        logoutLink.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Clear client-side storage
            clearClientStorage();
            
            // Continue with the logout action
            window.location.href = this.href;
        });
    }
}); 