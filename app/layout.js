import './globals.css';

export const metadata = {
  title: 'CalDAV to ICS',
  description: 'Simple CalDAV to ICS converter',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
