import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "../../components/ui/Button";
import { ROUTES } from "../../utils/constants";

export const NotFoundPage = () => {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="text-center">
        <h1 className="text-8xl font-bold text-primary mb-4">404</h1>
        <h2 className="text-2xl font-semibold mb-2">{t("notFoundPage.page_not_found")}</h2>
        <p className="text-muted-foreground mb-8 max-w-md mx-auto">
          {t("notFoundPage.the_page_you_re_looking_for_doesn_t")}
        </p>
        <Link to={ROUTES.HOME}>
          <Button variant="primary">{t("notFoundPage.go_back_home")}</Button>
        </Link>
      </div>
    </div>
  );
};
