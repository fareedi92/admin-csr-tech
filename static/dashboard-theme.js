tailwind.config = {
    corePlugins: { preflight: false },
    theme: {
        extend: {
            fontFamily: { sans: ['Inter', 'sans-serif'] },
            colors: {
                brand: {
                    50: '#fefce8',
                    100: '#fef9c3',
                    200: '#fef08a',
                    300: '#fde047',
                    400: '#facc15',
                    500: '#eab308',
                    600: '#ca8a04',
                    700: '#a16207',
                    800: '#854d0e',
                    900: '#713f12',
                },
                sf: '#ffffff',
                'sf-2': '#f8fafc',
                'sf-3': '#f1f5f9',
                sidebar: '#facc15',
                bd: 'rgba(0, 0, 0, 0.12)',
            },
            backgroundImage: {
                'dashboard-shell': 'linear-gradient(180deg, #ffffff 0%, #fefce8 100%)',
                'brand-gradient': 'linear-gradient(135deg, #facc15 0%, #eab308 100%)',
            },
            boxShadow: {
                brand: '0 12px 28px rgba(234, 179, 8, 0.25)',
            },
        },
    },
};
